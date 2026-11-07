import hashlib
import hmac
import ipaddress
import logging
import secrets
from datetime import timedelta
from functools import lru_cache
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from .models import AuditEntry, Event, Passport, RateBucket, Redemption, RedemptionTicket, ScanVoucher, Stamp, Stand

CONSENT_VERSION = "marketing-v2-celular-provisoria"
IMAGE_CONSENT_VERSION = "imagem-v1-circuito-provisoria"
security_log = logging.getLogger("passport.security")


def digest(kind, value):
    return salted_hmac("passaporte." + kind, str(value), algorithm="sha256").hexdigest()


def rate_key(kind, value):
    return digest("rate." + kind, value)


def limit(kind, value, maximum, seconds=600):
    now = timezone.now()
    key = rate_key(kind, value)
    first_block = False
    with transaction.atomic():
        bucket, _ = RateBucket.objects.select_for_update().get_or_create(
            key=key, defaults={"window_start": now, "count": 0}
        )
        if now >= bucket.window_start + timedelta(seconds=seconds):
            bucket.window_start, bucket.count = now, 0
        allowed = bucket.count < maximum
        if allowed:
            bucket.count += 1
        elif bucket.count == maximum:
            # Marca o primeiro bloqueio da janela para registrar um único aviso, não um por tentativa.
            bucket.count += 1
            first_block = True
        bucket.save(update_fields=["window_start", "count"])
    if first_block:
        # Nunca registre o valor (nome de usuário, endereço, contato): apenas o tipo e a chave derivada.
        security_log.warning(
            "Limite de tentativas atingido: tipo=%s chave=%s ate=%s",
            kind, key, (bucket.window_start + timedelta(seconds=seconds)).isoformat(timespec="seconds"),
        )
    return allowed


def blocked_until(kind, value, maximum, seconds=600):
    """Fim do bloqueio em vigor, ou None se novas tentativas são aceitas."""
    bucket = RateBucket.objects.filter(key=rate_key(kind, value)).first()
    if not bucket or bucket.count < maximum:
        return None
    end = bucket.window_start + timedelta(seconds=seconds)
    return end if end > timezone.now() else None


def limit_reset(kind, value):
    return RateBucket.objects.filter(key=rate_key(kind, value)).delete()[0] > 0


MAX_FORWARDED_ENTRIES = 20


@lru_cache(maxsize=8)
def _proxy_networks(entries):
    return tuple(ipaddress.ip_network(entry) for entry in entries)


def _parse_ip(value):
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if address.version == 6 and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


def client_address(request):
    """Endereço usado nos limites de tentativas.

    Regra (documentada no README, "Implantação atrás de proxy"):
    - Sem TRUSTED_PROXIES, ou se REMOTE_ADDR não pertence a um proxy de confiança,
      X-Forwarded-For é ignorado e vale REMOTE_ADDR. Assim, um acesso direto não escolhe
      o endereço, mesmo enviando o cabeçalho.
    - Vindo de proxy de confiança, a cadeia é lida da direita para a esquerda, pulando
      proxies de confiança; o primeiro endereço que não é de confiança é o cliente.
      Entradas mais à esquerda, que o cliente pode ter forjado, nunca são lidas.
    - Cadeia inconsistente (cabeçalho ausente, entrada inválida ou com porta, cadeia longa
      demais): vale REMOTE_ADDR, isto é, o endereço do proxy. Todos os pedidos nessa
      situação dividem um contador, o que é mais restritivo, nunca mais permissivo.
    - Se todas as entradas forem de proxies de confiança, vale a mais à esquerda.
    """
    remote_raw = request.META.get("REMOTE_ADDR") or "unknown"
    remote = _parse_ip(remote_raw)
    trusted = _proxy_networks(tuple(getattr(settings, "TRUSTED_PROXIES", ())))
    if remote is None:
        return remote_raw
    if not trusted or not any(remote in net for net in trusted):
        return str(remote)
    header = request.META.get("HTTP_X_FORWARDED_FOR", "")
    chain = [part for part in header.split(",")]
    if not header.strip() or len(chain) > MAX_FORWARDED_ENTRIES:
        return str(remote)
    candidate = None
    for raw in reversed(chain):
        address = _parse_ip(raw)
        if address is None:
            return str(remote)
        candidate = address
        if not any(address in net for net in trusted):
            return str(address)
    return str(candidate)


def station_code(stand, at=None):
    at = at or timezone.now()
    slot = int(at.timestamp()) // 60
    msg = f"{stand.event_id}:{stand.pk}:{slot}"
    raw = bytes.fromhex(digest("station", msg))
    return f"{int.from_bytes(raw[:8], 'big') % 1_000_000:06d}"


def valid_station_code(stand, code, at=None):
    at = at or timezone.now()
    # A janela anterior evita falhas na troca do minuto; validade efetiva de até 120 s.
    return any(hmac.compare_digest(station_code(stand, at - timedelta(seconds=s)), code) for s in (0, 60))


def verify_pin(passport, pin):
    # Igualar a operação cara quando o contato não existe reduz diferenças de tempo.
    fallback = "pbkdf2_sha256$1000000$GXhLsbYZJOUcMtEwvfIUuJ$chfl1sSG/a2GEMzBRDmHZUUhON1+8WKWwkQitKh7HcE="
    return check_password(pin, passport.pin_hash if passport else fallback) and passport is not None


def eligible(passport):
    required = list(passport.event.stands.filter(active=True, required=True).values_list("pk", flat=True))
    if not required:
        return False
    return passport.stamps.filter(stand_id__in=required).count() == len(required)


def stamp_ready_at(passport):
    """Momento em que o intervalo permite outro carimbo; None antes do primeiro."""
    if not passport.last_stamp_at:
        return None
    return passport.last_stamp_at + timedelta(seconds=passport.event.gap_seconds)


def record_stamp(passport_id, version, stand_id, code, now=None):
    now = now or timezone.now()
    with transaction.atomic():
        p = Passport.objects.select_for_update().select_related("event").get(pk=passport_id)
        if p.session_version != version:
            return "session", 0
        stand = Stand.objects.filter(pk=stand_id, event=p.event, active=True).first()
        if not p.event.active or not stand or not valid_station_code(stand, code, now):
            return "invalid", 0
        return _stamp_locked(p, stand, now)


def _stamp_locked(p, stand, now):
    """Regras de duplicidade e intervalo; exige o passaporte bloqueado na transação corrente."""
    if Stamp.objects.filter(passport=p, stand=stand).exists():
        return "duplicate", 0
    ready_at = stamp_ready_at(p)
    if ready_at:
        remaining = (ready_at - now).total_seconds()
        if remaining > 0:
            return "wait", int(remaining + 0.999)
    Stamp.objects.create(passport=p, stand=stand, created_at=now)
    p.last_stamp_at = now
    p.save(update_fields=["last_stamp_at"])
    return "ok", 0


VOUCHER_SECONDS = 300


def issue_scan_voucher(stand, code, now=None):
    """Comprovante para um QR válido no momento da leitura. Devolve (token, voucher) ou (None, None).

    QR inválido ou expirado, estande inativo ou evento inativo não geram comprovante.
    """
    now = now or timezone.now()
    if not stand.active or not stand.event.active or not valid_station_code(stand, code, now):
        return None, None
    # Limpeza oportunista: comprovantes vencidos há mais de um dia não servem para nada.
    ScanVoucher.objects.filter(expires_at__lt=now - timedelta(days=1)).delete()
    token = secrets.token_urlsafe(32)
    voucher = ScanVoucher.objects.create(
        token_digest=digest("scan_voucher", token), event=stand.event, stand=stand,
        created_at=now, expires_at=now + timedelta(seconds=VOUCHER_SECONDS),
    )
    return token, voucher


def find_scan_voucher(token, now=None):
    """Comprovante ainda utilizável (não consumido, no prazo, evento e estande ativos) ou None."""
    if not token:
        return None
    now = now or timezone.now()
    return ScanVoucher.objects.select_related("stand", "event").filter(
        token_digest=digest("scan_voucher", token), consumed_at__isnull=True, expires_at__gt=now,
        event__active=True, stand__active=True,
    ).first()


def record_stamp_with_voucher(passport_id, version, token, now=None):
    """Consome o comprovante uma única vez, na mesma transação do carimbo.

    Resultados: ok, wait (comprovante mantido até expirar), duplicate (comprovante encerrado), expired,
    used, invalid, session. Ordem de bloqueio: comprovante e depois passaporte.
    """
    now = now or timezone.now()
    with transaction.atomic():
        voucher = ScanVoucher.objects.select_for_update().filter(token_digest=digest("scan_voucher", token or "")).first()
        if not voucher:
            return "invalid", 0, None
        if voucher.consumed_at:
            return "used", 0, voucher
        if voucher.expires_at <= now:
            return "expired", 0, voucher
        p = Passport.objects.select_for_update().select_related("event").get(pk=passport_id)
        if p.session_version != version:
            return "session", 0, voucher
        stand = Stand.objects.filter(pk=voucher.stand_id, event=p.event, active=True).first()
        if not p.event.active or p.event_id != voucher.event_id or not stand:
            return "invalid", 0, voucher
        result, seconds = _stamp_locked(p, stand, now)
        if result in ("ok", "duplicate"):
            voucher.consumed_at, voucher.consumed_by = now, p
            voucher.save(update_fields=["consumed_at", "consumed_by"])
        return result, seconds, voucher


PIN_RESET_METHODS = {
    "aparelho": "Visitante mostrou, no próprio aparelho, o número cadastrado",
    "ligacao": "Ligação ou mensagem de teste para o número cadastrado recebida no aparelho do visitante",
    "excecao_gestor": "Exceção autorizada por gestor, com justificativa",
}
# Reenvio acidental (toque duplo, voltar e reenviar): não gera um segundo PIN logo em seguida.
PIN_RESET_COOLDOWN_SECONDS = 60


def reset_visitor_pin(passport_id, event_id, operator, method, justification=""):
    """Gera um PIN aleatório de 6 dígitos, grava só o hash e invalida as sessões do visitante.

    Devolve (status, pin): ("ok", pin), ("recent", None) ou ("invalid", None). O PIN nunca é registrado
    em log ou auditoria.
    """
    if method not in PIN_RESET_METHODS:
        return "invalid", None
    pin = f"{secrets.randbelow(1_000_000):06d}"
    pin_hash = make_password(pin)  # custo do hash fora do bloqueio
    with transaction.atomic():
        p = Passport.objects.select_for_update().filter(pk=passport_id, event_id=event_id, event__active=True).first()
        if not p:
            return "invalid", None
        recent = AuditEntry.objects.filter(
            action="visitor.pin_reset", target=p.public_id,
            created_at__gt=timezone.now() - timedelta(seconds=PIN_RESET_COOLDOWN_SECONDS),
        ).exists()
        if recent:
            return "recent", None
        p.pin_hash = pin_hash
        p.session_version += 1
        p.save(update_fields=["pin_hash", "session_version"])
        detail = {"metodo": method}
        if justification:
            detail["justificativa"] = justification[:300]
        audit(operator, "visitor.pin_reset", p.public_id, **detail)
    security_log.info("PIN de visitante redefinido: passaporte_id=%s por_id=%s metodo=%s", p.pk, operator.pk, method)
    return "ok", pin


def issue_ticket(passport_id, version):
    with transaction.atomic():
        p = Passport.objects.select_for_update().select_related("event").get(pk=passport_id)
        if p.session_version != version or not p.event.active or not eligible(p) or Redemption.objects.filter(passport=p).exists():
            return None
        code = secrets.token_hex(5).upper()
        RedemptionTicket.objects.update_or_create(
            passport=p,
            defaults={"code_digest": digest("ticket", code), "expires_at": timezone.now() + timedelta(minutes=5)},
        )
        return code


def find_ticket(code):
    ticket = RedemptionTicket.objects.select_related("passport", "passport__event").filter(
        code_digest=digest("ticket", code.upper()), expires_at__gt=timezone.now()
    ).first()
    if not ticket or not ticket.passport.event.active or not eligible(ticket.passport):
        return None
    return ticket


def redeem(code, staff):
    ticket = find_ticket(code)
    if not ticket:
        return "invalid"
    with transaction.atomic():
        p = Passport.objects.select_for_update().select_related("event").get(pk=ticket.passport_id)
        ticket = RedemptionTicket.objects.filter(
            passport=p, code_digest=digest("ticket", code.upper()), expires_at__gt=timezone.now()
        ).first()
        if not ticket or not p.event.active or not eligible(p):
            return "invalid"
        _, created = Redemption.objects.get_or_create(passport=p, defaults={"staff": staff})
        return "ok" if created else "duplicate"


def audit(user, action, target="", **detail):
    return AuditEntry.objects.create(user=user, action=action, target=str(target)[:40], detail=detail)


def mask_contact(contact):
    """Mostra o suficiente para conferir com o visitante, sem expor o número completo."""
    if "@" in contact:
        local, _, domain = contact.partition("@")
        return f"{local[:1]}•••@•••{domain[-4:]}" if local else "•••"
    digits = "".join(ch for ch in contact if ch.isdigit())
    if len(digits) == 13 and digits.startswith("55"):
        digits = digits[2:]
    if len(digits) == 11:
        return f"({digits[:2]}) •••••-••{digits[-2:]}"
    return f"•••{digits[-2:]}" if len(digits) >= 4 else "•••"


MIN_GAP_MINUTES, MAX_GAP_MINUTES = 1, 60


def set_gap_minutes(event_id, minutes, user):
    """Altera Event.gap_seconds (a única fonte do intervalo) e registra quem alterou."""
    if not MIN_GAP_MINUTES <= minutes <= MAX_GAP_MINUTES:
        raise ValueError("intervalo fora do limite")
    with transaction.atomic():
        event = Event.objects.select_for_update().get(pk=event_id)
        old, new = event.gap_seconds, minutes * 60
        if old != new:
            event.gap_seconds = new
            event.save(update_fields=["gap_seconds"])
            audit(user, "event.gap", event.pk, de_segundos=old, para_segundos=new)
    if old != new:
        security_log.info("Intervalo alterado: evento_id=%s de=%s para=%s por_id=%s", event_id, old, new, user.pk)
    return old, new
