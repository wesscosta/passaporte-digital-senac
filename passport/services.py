import hashlib
import hmac
import secrets
from datetime import timedelta
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from .models import Passport, RateBucket, Redemption, RedemptionTicket, Stamp, Stand

CONSENT_VERSION = "marketing-v2-celular-provisoria"


def digest(kind, value):
    return salted_hmac("passaporte." + kind, str(value), algorithm="sha256").hexdigest()


def limit(kind, value, maximum, seconds=600):
    now = timezone.now()
    key = digest("rate." + kind, value)
    with transaction.atomic():
        bucket, _ = RateBucket.objects.select_for_update().get_or_create(
            key=key, defaults={"window_start": now, "count": 0}
        )
        if now >= bucket.window_start + timedelta(seconds=seconds):
            bucket.window_start, bucket.count = now, 0
        allowed = bucket.count < maximum
        if allowed:
            bucket.count += 1
        bucket.save(update_fields=["window_start", "count"])
    return allowed


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
        if p.last_stamp_at:
            remaining = (p.last_stamp_at + timedelta(seconds=p.event.gap_seconds) - now).total_seconds()
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
