import hashlib
import logging
import hmac
import secrets
from datetime import timedelta
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from .models import AuditEntry, Event, Passport, RateBucket, Redemption, RedemptionTicket, Stamp, Stand

CONSENT_VERSION = "marketing-v2-celular-provisoria"
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


def client_address(request):
    # Apenas REMOTE_ADDR; encaminhamento de proxy requer configuração confiável.
    return request.META.get("REMOTE_ADDR", "unknown")


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
