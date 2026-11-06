import base64
import io
import re
from datetime import timedelta
from functools import wraps
import qrcode
import qrcode.image.svg
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.http import HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from .forms import ManualStampForm, RecoveryForm, RegistrationForm, TicketLookupForm
from .models import Event, Passport, Redemption, Stand
from .services import (
    CONSENT_VERSION, digest, eligible, find_ticket, issue_ticket, limit,
    record_stamp, redeem, stamp_ready_at, station_code, valid_station_code, verify_pin,
)


def current_event():
    events = list(Event.objects.filter(active=True)[:2])
    return events[0] if len(events) == 1 else None


def participant(request):
    pk, version = request.session.get("passport_id"), request.session.get("passport_version")
    if not pk or not version:
        return None
    p = Passport.objects.select_related("event").filter(pk=pk, session_version=version, event__active=True).first()
    if not p:
        request.session.pop("passport_id", None)
        request.session.pop("passport_version", None)
        request.session.pop("ticket_code", None)
    return p


def participant_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        p = participant(request)
        if not p:
            return redirect("recover")
        return view(request, p, *args, **kwargs)
    return wrapped


def sign_in_participant(request, p):
    request.session.cycle_key()
    request.session["passport_id"] = p.pk
    request.session["passport_version"] = p.session_version
    request.session.pop("ticket_code", None)
    pending = request.session.pop("pending_scan", None)
    if pending and isinstance(pending, list) and len(pending) == 2:
        return redirect("scan_stamp", stand_id=pending[0], code=pending[1])
    return redirect("passport")


def pending_stand(request, event):
    pending = request.session.get("pending_scan")
    if not (isinstance(pending, list) and len(pending) == 2):
        return None
    return Stand.objects.filter(pk=pending[0], event=event, active=True).first()


def next_stamp_at(p, now=None):
    ready = stamp_ready_at(p)
    if not ready or ready <= (now or timezone.now()):
        return None
    # Arredonda para o minuto seguinte: exibir 14:32 para 14:32:40 levaria a uma tentativa recusada.
    if ready.second or ready.microsecond:
        ready = ready.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return ready


def interval_label(seconds):
    """Descreve o intervalo configurado do evento; None quando não há intervalo."""
    if not seconds:
        return None
    minutes, secs = divmod(seconds, 60)
    if not minutes:
        return "1 segundo" if secs == 1 else f"{secs} segundos"
    label = "1 minuto" if minutes == 1 else f"{minutes} minutos"
    return f"{label} e {secs} s" if secs else label


def client_address(request):
    # Apenas REMOTE_ADDR; encaminhamento de proxy requer configuração confiável.
    return request.META.get("REMOTE_ADDR", "unknown")


def contact_digests(contact):
    # Um celular legado pode ter sido salvo com o prefixo 55; não altere os dados.
    values = [contact]
    if contact.isascii() and contact.isdigit() and len(contact) == 11:
        values.append("55" + contact)
    return [digest("contact", value) for value in values]


@never_cache
def home(request):
    event = current_event()
    return render(request, "passport/home.html", {
        "event": event, "p": participant(request), "gap": interval_label(event.gap_seconds) if event else None,
    })


@never_cache
def register(request):
    event = current_event()
    if not event:
        return render(request, "passport/unavailable.html", status=503)
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not limit("register.ip", client_address(request), 100):
            form.add_error(None, "Muitas tentativas. Aguarde alguns minutos e tente novamente.")
        else:
            data = form.cleaned_data
            already_registered = Passport.objects.filter(
                event=event, contact_digest__in=contact_digests(data["contact"])
            ).exists()
            if already_registered:
                form.add_error(None, "Não foi possível cadastrar. Confira os dados ou tente recuperar o acesso.")
            else:
                pin_hash = make_password(data["pin"])
                try:
                    with transaction.atomic():
                        p = Passport.objects.create(
                            event=event, name=data["name"], contact=data["contact"],
                            contact_digest=digest("contact", data["contact"]),
                            pin_hash=pin_hash,
                            consent_marketing=data["marketing"], consent_version=CONSENT_VERSION,
                            consent_recorded_at=timezone.now(),
                        )
                    return sign_in_participant(request, p)
                except IntegrityError:
                    form.add_error(None, "Não foi possível cadastrar. Confira os dados ou tente recuperar o acesso.")
    return render(request, "passport/register.html", {"form": form, "event": event, "pending_stand": pending_stand(request, event)})


@never_cache
def recover(request):
    event = current_event()
    if not event:
        return render(request, "passport/unavailable.html", status=503)
    form = RecoveryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        contact = form.cleaned_data["contact"]
        ip_ok = limit("recovery.ip", client_address(request), 100)
        account_ok = limit("recovery.account", f"{event.pk}:{contact}", 5)
        if ip_ok and account_ok:
            candidates = list(Passport.objects.filter(
                event=event, contact_digest__in=contact_digests(contact)
            ).order_by("pk")[:2])
            if not candidates:
                verify_pin(None, form.cleaned_data["pin"])
            matches = [candidate for candidate in candidates if verify_pin(candidate, form.cleaned_data["pin"])]
            if len(matches) == 1:
                candidate = matches[0]
                # Não mantenha o bloqueio de banco durante a verificação custosa do PIN.
                with transaction.atomic():
                    p = Passport.objects.select_for_update().filter(pk=candidate.pk, event__active=True).first()
                    if p and p.pin_hash == candidate.pin_hash:
                        p.session_version += 1
                        p.save(update_fields=["session_version"])
                        return sign_in_participant(request, p)
        form.add_error(None, "Não foi possível recuperar o acesso. Confira os dados ou aguarde e tente novamente.")
    return render(request, "passport/recover.html", {"form": form, "event": event, "pending_stand": pending_stand(request, event)})


@never_cache
@participant_required
def passport_page(request, p):
    stands = list(p.event.stands.filter(active=True))
    visited = set(p.stamps.values_list("stand_id", flat=True))
    rows = [{"stand": s, "visited": s.pk in visited} for s in stands]
    redeemed = Redemption.objects.filter(passport=p).exists()
    code = request.session.get("ticket_code")
    ticket = find_ticket(code) if code else None
    if not ticket or ticket.passport_id != p.pk or redeemed:
        code = None
        request.session.pop("ticket_code", None)
    qr = None
    if code:
        url = request.build_absolute_uri(reverse("prize_review", args=[code]))
        image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=3)
        output = io.BytesIO()
        image.save(output)
        qr = base64.b64encode(output.getvalue()).decode("ascii")
    done = len(visited.intersection({s.pk for s in stands}))
    return render(request, "passport/passport.html", {
        "p": p, "rows": rows, "done": done, "total": len(stands),
        "eligible": eligible(p), "redeemed": redeemed, "ticket_code": code, "ticket_qr": qr,
        "next_stamp_at": next_stamp_at(p) if done < len(stands) else None,
        "gap": interval_label(p.event.gap_seconds),
    })


def report_stamp(request, p, stand_id, code):
    if not limit("stamp.passport", str(p.pk), 30):
        messages.error(request, "Muitas tentativas. Aguarde alguns minutos e tente novamente.")
        return "limited"
    result, seconds = record_stamp(p.pk, request.session.get("passport_version"), stand_id, code)
    if result == "ok":
        messages.success(request, "Carimbo registrado com sucesso.")
    elif result == "duplicate":
        messages.info(request, "Este estande já foi registrado. O intervalo não foi reiniciado.")
    elif result == "wait":
        minutes, secs = divmod(seconds, 60)
        messages.error(request, f"Aguarde {minutes}min {secs:02d}s para o próximo carimbo.")
    elif result == "session":
        messages.error(request, "Sua sessão foi substituída. Recupere o acesso novamente.")
    else:
        messages.error(request, "Código inválido ou expirado. Peça o código atualizado no estande.")
    return result


@never_cache
@participant_required
def manual_stamp(request, p):
    form = ManualStampForm(request.POST or None, event=p.event)
    if request.method == "POST" and form.is_valid():
        report_stamp(request, p, form.cleaned_data["stand"].pk, form.cleaned_data["code"])
        return redirect("passport")
    return render(request, "passport/manual_stamp.html", {"form": form, "next_stamp_at": next_stamp_at(p)})


@never_cache
def scan_stamp(request, stand_id, code):
    if not re.fullmatch(r"[0-9]{6}", code):
        return render(request, "passport/unavailable.html", status=404)
    p = participant(request)
    if not p:
        # Primeiro contato costuma ser o QR do estande: oferecer cadastro, não só recuperação.
        event = current_event()
        stand = Stand.objects.filter(pk=stand_id, event=event, active=True).first() if event else None
        if not stand:
            return render(request, "passport/unavailable.html", status=404)
        request.session["pending_scan"] = [stand.pk, code]
        return render(request, "passport/scan_entry.html", {"stand": stand})
    stand = get_object_or_404(Stand, pk=stand_id, event=p.event, active=True)
    if request.method == "POST":
        if report_stamp(request, p, stand.pk, code) == "invalid":
            return redirect(reverse("manual_stamp") + "#leitor")
        return redirect("passport")
    return render(request, "passport/scan_confirm.html", {
        "stand": stand, "expired": not valid_station_code(stand, code), "next_stamp_at": next_stamp_at(p),
    })


@never_cache
@participant_required
def issue_redemption(request, p):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    code = issue_ticket(p.pk, request.session.get("passport_version"))
    if code:
        request.session["ticket_code"] = code
        messages.success(request, "Código de retirada gerado. Apresente-o no setor de premiação.")
    else:
        messages.error(request, "Ainda não é possível gerar o código de retirada.")
    return redirect("passport")


def staff_only(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            return HttpResponseForbidden("Acesso restrito à equipe autorizada.")
        return view(request, *args, **kwargs)
    return wrapped


def prize_allowed(user):
    return user.is_superuser or (user.is_staff and user.groups.filter(name="Premiação").exists())


@never_cache
@staff_only
def staff_home(request):
    stands = Stand.objects.filter(active=True, event__active=True)
    if not request.user.is_superuser:
        stands = stands.filter(staff=request.user)
    return render(request, "passport/staff_home.html", {"stands": stands, "prize_allowed": prize_allowed(request.user)})


@never_cache
@staff_only
def station(request, stand_id):
    stand = get_object_or_404(Stand, pk=stand_id, active=True, event__active=True)
    if not request.user.is_superuser and not stand.staff.filter(pk=request.user.pk).exists():
        return HttpResponseForbidden("Este estande não está atribuído à sua conta.")
    now = timezone.now()
    code = station_code(stand, now)
    url = request.build_absolute_uri(reverse("scan_stamp", args=[stand.pk, code]))
    svg = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=3)
    output = io.BytesIO()
    svg.save(output)
    qr = base64.b64encode(output.getvalue()).decode("ascii")
    milliseconds = (60 - (int(now.timestamp()) % 60)) * 1000 + 250
    return render(request, "passport/station.html", {"stand": stand, "code": code, "qr": qr, "milliseconds": milliseconds})


@never_cache
@staff_only
def prize_lookup(request):
    if not prize_allowed(request.user):
        return HttpResponseForbidden("Acesso restrito à equipe de premiação.")
    form = TicketLookupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        return redirect("prize_review", code=form.cleaned_data["code"])
    return render(request, "passport/prize_lookup.html", {"form": form})


@never_cache
@staff_only
def prize_review(request, code):
    if not prize_allowed(request.user):
        return HttpResponseForbidden("Acesso restrito à equipe de premiação.")
    if not re.fullmatch(r"[0-9A-Fa-f]{10}", code):
        return render(request, "passport/ticket_invalid.html", status=404)
    code = code.upper()
    ticket = find_ticket(code)
    if not ticket:
        return render(request, "passport/ticket_invalid.html", status=404)
    already = Redemption.objects.filter(passport=ticket.passport).exists()
    if request.method == "POST":
        status = redeem(code, request.user)
        if status == "ok":
            messages.success(request, "Entrega registrada.")
        elif status == "duplicate":
            messages.info(request, "A entrega já havia sido registrada.")
        else:
            messages.error(request, "Código inválido ou expirado.")
        return redirect("prize_review", code=code)
    return render(request, "passport/prize_review.html", {"ticket": ticket, "already": already, "code": code})
