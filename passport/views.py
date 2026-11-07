import base64
import csv
import io
import re
from datetime import timedelta
from functools import wraps
import qrcode
import qrcode.image.svg
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Q
from .areas import AREAS, area_key
from .forms import (
    IntervalForm, ManualStampForm, PassportSearchForm, RecoveryForm, RegistrationForm, TicketLookupForm, normalize_contact,
)
from .ids import normalize_public_id
from .models import Event, Passport, Redemption, Stamp, Stand
from .permissions import (
    assigned_stands, can_search_passports, forbidden, is_manager, manager_only, prize_allowed, prize_only, search_only,
    staff_only,
)
from .services import (
    CONSENT_VERSION, IMAGE_CONSENT_VERSION, audit, client_address, digest, eligible, find_ticket, issue_ticket, limit, mask_contact,
    record_stamp, redeem, set_gap_minutes, stamp_ready_at, station_code, valid_station_code, verify_pin,
)


def current_event():
    events = list(Event.objects.filter(active=True)[:2])
    return events[0] if len(events) == 1 else None


SESSION_REPLACED_MESSAGE = (
    "Seu passaporte foi aberto em outro aparelho ou o PIN foi redefinido pela organização. Entre novamente para continuar."
)


def _forget_participant(request):
    for key in ("passport_id", "passport_version", "ticket_code"):
        request.session.pop(key, None)


def participant_state(request):
    """Devolve (passaporte, estado): "ok", "paused" (evento do passaporte pausado) ou "none"."""
    pk, version = request.session.get("passport_id"), request.session.get("passport_version")
    if not pk or not version:
        return None, "none"
    p = Passport.objects.select_related("event").filter(pk=pk).first()
    if not p:
        _forget_participant(request)
        return None, "none"
    if p.session_version != version:
        # Entrada em outro aparelho ou PIN redefinido: explica em vez de apenas pedir o PIN.
        _forget_participant(request)
        messages.warning(request, SESSION_REPLACED_MESSAGE)
        return None, "none"
    if not p.event.active:
        # Pausa do evento não desconecta: a sessão volta a valer quando o evento for reativado.
        # Se outro evento estiver ativo, este passaporte não serve mais e a sessão é encerrada.
        if Event.objects.filter(active=True).exists():
            _forget_participant(request)
            return None, "none"
        return None, "paused"
    return p, "ok"


def participant(request):
    return participant_state(request)[0]


def participant_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        p, state = participant_state(request)
        if state == "paused":
            return render(request, "passport/paused.html", status=503)
        if not p:
            return redirect("recover")
        return view(request, p, *args, **kwargs)
    return wrapped


def sign_in_participant(request, p, *, remember=True):
    request.session.cycle_key()
    request.session.set_expiry(None if remember else 0)
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


def round_up_minute(moment):
    # Exibir 14:32 para 14:32:40 levaria a uma tentativa recusada; o visitante vê sempre o minuto seguinte.
    if moment.second or moment.microsecond:
        return moment.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return moment


def next_stamp_at(p, now=None):
    ready = stamp_ready_at(p)
    if not ready or ready <= (now or timezone.now()):
        return None
    return round_up_minute(ready)


def interval_label(seconds):
    """Descreve o intervalo configurado do evento; None quando não há intervalo."""
    if not seconds:
        return None
    minutes, secs = divmod(seconds, 60)
    if not minutes:
        return "1 segundo" if secs == 1 else f"{secs} segundos"
    label = "1 minuto" if minutes == 1 else f"{minutes} minutos"
    return f"{label} e {secs} s" if secs else label


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
                form.add_error(None, "Não foi possível cadastrar. Confira os dados ou entre no passaporte, se já tiver um.")
            else:
                pin_hash = make_password(data["pin"])
                try:
                    with transaction.atomic():
                        recorded_at = timezone.now()
                        p = Passport.objects.create(
                            event=event, name=data["name"], contact=data["contact"],
                            contact_digest=digest("contact", data["contact"]),
                            pin_hash=pin_hash, interest_segment=data["interest_segment"],
                            consent_marketing=data["marketing"], consent_version=CONSENT_VERSION,
                            consent_recorded_at=recorded_at,
                            consent_image=data["image_consent"], consent_image_version=IMAGE_CONSENT_VERSION,
                            consent_image_recorded_at=recorded_at,
                        )
                    return sign_in_participant(request, p)
                except IntegrityError:
                    form.add_error(None, "Não foi possível cadastrar. Confira os dados ou entre no passaporte, se já tiver um.")
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
                        return sign_in_participant(request, p, remember=form.cleaned_data["remember"])
        form.add_error(None, "Não foi possível entrar. Confira os dados ou aguarde e tente novamente.")
    return render(request, "passport/recover.html", {"form": form, "event": event, "pending_stand": pending_stand(request, event)})


@never_cache
@participant_required
def passport_page(request, p):
    stands = list(p.event.stands.filter(active=True))
    stamped_at = dict(p.stamps.values_list("stand_id", "created_at"))
    visited = set(stamped_at)
    just_stamped = request.session.pop("just_stamped", None)
    rows = [
        {"stand": s, "area": area_key(s), "visited": s.pk in visited, "stamped_at": stamped_at.get(s.pk),
         "new": s.pk == just_stamped}
        for s in stands
    ]
    redeemed = Redemption.objects.filter(passport=p).exists()
    code = request.session.get("ticket_code")
    ticket = find_ticket(code) if code else None
    if not ticket or ticket.passport_id != p.pk or redeemed:
        code = None
        request.session.pop("ticket_code", None)
    qr, ticket_expires_at = None, None
    if code:
        ticket_expires_at = ticket.expires_at
        url = request.build_absolute_uri(reverse("prize_review", args=[code]))
        image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=3)
        output = io.BytesIO()
        image.save(output)
        qr = base64.b64encode(output.getvalue()).decode("ascii")
    done = len(visited.intersection({s.pk for s in stands}))
    return render(request, "passport/passport.html", {
        "p": p, "rows": rows, "done": done, "total": len(stands),
        "eligible": eligible(p), "redeemed": redeemed, "ticket_code": code, "ticket_qr": qr,
        "ticket_expires_at": ticket_expires_at, "required_total": sum(1 for s in stands if s.required),
        "next_stamp_at": next_stamp_at(p) if done < len(stands) else None,
        "gap": interval_label(p.event.gap_seconds),
        "celebrate_stamp": any(row["new"] and row["visited"] for row in rows),
    })


INVALID_CODE_MESSAGE = "Código inválido ou expirado. Peça o código atualizado no estande."


def report_stamp(request, p, stand_id, code, *, notify_invalid=True):
    if not limit("stamp.passport", str(p.pk), 30):
        messages.error(request, "Muitas tentativas. Aguarde alguns minutos e tente novamente.")
        return "limited"
    result, seconds = record_stamp(p.pk, request.session.get("passport_version"), stand_id, code)
    if result == "ok":
        stamp = Stamp.objects.select_related("stand").get(passport=p, stand_id=stand_id)
        request.session["just_stamped"] = stand_id
        messages.success(request, f"{stamp.stand.name} carimbado às {timezone.localtime(stamp.created_at):%H:%M}.")
    elif result == "duplicate":
        stamp = Stamp.objects.get(passport=p, stand_id=stand_id)
        messages.info(request, f"Você já carimbou este estande às {timezone.localtime(stamp.created_at):%H:%M}. O intervalo não foi reiniciado.")
    elif result == "wait":
        # Mesmo cálculo e arredondamento do passaporte, para não prometer dois horários diferentes.
        p.refresh_from_db(fields=["last_stamp_at"])
        p.event.refresh_from_db(fields=["gap_seconds"])
        release = next_stamp_at(p) or round_up_minute(timezone.now() + timedelta(seconds=seconds))
        messages.warning(request, f"Aguarde o intervalo entre carimbos. Seu próximo carimbo fica disponível às {timezone.localtime(release):%H:%M}.")
    elif result == "session":
        messages.warning(request, SESSION_REPLACED_MESSAGE)
    elif notify_invalid:
        messages.error(request, INVALID_CODE_MESSAGE)
    return result


@never_cache
@participant_required
def manual_stamp(request, p):
    form = ManualStampForm(request.POST or None, event=p.event)
    if request.method == "POST" and form.is_valid():
        result = report_stamp(request, p, form.cleaned_data["stand"].pk, form.cleaned_data["code"], notify_invalid=False)
        if result != "invalid":
            return redirect("passport")
        # Mantém o estande escolhido e o código para correção, sem sair da tela.
        form.add_error("code", "Código inválido ou expirado. Confira o estande escolhido e digite o código que aparece agora na tela.")
    return render(request, "passport/manual_stamp.html", {"form": form, "next_stamp_at": next_stamp_at(p)})


@never_cache
def scan_stamp(request, stand_id, code):
    if not re.fullmatch(r"[0-9]{6}", code):
        return render(request, "passport/unavailable.html", status=404)
    p, state = participant_state(request)
    if state == "paused":
        # Mesmo comportamento das demais telas do visitante: nada é registrado e a sessão é mantida.
        return render(request, "passport/paused.html", status=503)
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
    stamp = Stamp.objects.filter(passport=p, stand=stand).first()
    return render(request, "passport/scan_confirm.html", {
        "stand": stand, "stamp": stamp, "expired": not stamp and not valid_station_code(stand, code),
        "next_stamp_at": next_stamp_at(p),
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
        # Leva direto ao código: depois de gerar, ele ficava abaixo da dobra no celular.
        return redirect(reverse("passport") + "#codigo-retirada")
    messages.error(request, "Ainda não é possível gerar o código de retirada.")
    return redirect("passport")


@never_cache
@staff_only
def staff_home(request):
    user = request.user
    stands = assigned_stands(user, Stand.objects.filter(active=True, event__active=True))
    return render(request, "passport/staff_home.html", {
        "stands": stands, "prize_allowed": prize_allowed(user),
        "can_search": can_search_passports(user), "is_manager": is_manager(user),
    })


@never_cache
@staff_only
def station(request, stand_id):
    stand = get_object_or_404(Stand, pk=stand_id, active=True, event__active=True)
    if not assigned_stands(request.user, Stand.objects.filter(pk=stand.pk)).exists():
        return forbidden(request, "Este estande não está atribuído à sua conta.")
    now = timezone.now()
    code = station_code(stand, now)
    url = request.build_absolute_uri(reverse("scan_stamp", args=[stand.pk, code]))
    svg = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=3)
    output = io.BytesIO()
    svg.save(output)
    qr = base64.b64encode(output.getvalue()).decode("ascii")
    # Calcula a duração até a próxima janela com precisão de milissegundos.
    milliseconds = max(1, int((60 - (now.timestamp() % 60)) * 1000))
    return render(request, "passport/station.html", {"stand": stand, "code": code, "qr": qr, "milliseconds": milliseconds})


@never_cache
@prize_only
def prize_lookup(request):
    form = TicketLookupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        return redirect("prize_review", code=form.cleaned_data["code"])
    return render(request, "passport/prize_lookup.html", {"form": form})


@never_cache
@prize_only
def prize_review(request, code):
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


PAGE_SIZE = 20


def search_passports(event, term):
    """Devolve (queryset, tipo). Celular e identificador exigem correspondência exata; nome aceita trecho."""
    base = Passport.objects.filter(event=event)
    digits = re.sub(r"[^0-9]", "", term)
    if re.fullmatch(r"\+?[0-9().\s-]+", term) and len(digits) >= 10:
        try:
            contact = normalize_contact(term)
        except ValidationError:
            return base.none(), "celular"
        return base.filter(contact_digest__in=contact_digests(contact)), "celular"
    public_id = normalize_public_id(term)
    query = Q(name__icontains=term.strip())
    if public_id:
        query |= Q(public_id=public_id)
    return base.filter(query), "identificador" if public_id else "nome"


def with_progress(queryset):
    on_active = Q(stamps__stand__active=True)
    return queryset.annotate(
        stamps_done=Count("stamps", filter=on_active, distinct=True),
        required_done=Count("stamps", filter=on_active & Q(stamps__stand__required=True), distinct=True),
        redeemed=Exists(Redemption.objects.filter(passport=OuterRef("pk"))),
    )


def prize_status(p, required_total):
    if p.redeemed:
        return "redeemed"
    return "eligible" if required_total and p.required_done == required_total else "pending"


@never_cache
@require_safe
@search_only
def passport_search(request):
    event = current_event()
    if not event:
        return render(request, "passport/unavailable.html", status=503)
    form = PassportSearchForm(request.GET or None)
    page, kind, results = None, None, []
    stands = event.stands.filter(active=True)
    total, required_total = stands.count(), stands.filter(required=True).count()
    if form.is_bound and form.is_valid() and form.cleaned_data["q"]:
        if not limit("staff.search", str(request.user.pk), 120):
            form.add_error(None, "Muitas consultas em pouco tempo. Aguarde alguns minutos.")
        else:
            queryset, kind = search_passports(event, form.cleaned_data["q"])
            page = Paginator(with_progress(queryset).order_by("name", "pk"), PAGE_SIZE).get_page(request.GET.get("pagina"))
            results = [{"p": p, "contact": mask_contact(p.contact), "status": prize_status(p, required_total)} for p in page]
            # O termo pesquisado não é registrado: pode ser nome ou telefone.
            audit(request.user, "passport.search", tipo=kind, pagina=page.number, resultados=page.paginator.count)
    return render(request, "passport/staff_search.html", {
        "form": form, "page": page, "searched": page is not None, "results": results, "kind": kind, "total": total, "required_total": required_total,
    })


@never_cache
@require_safe
@search_only
def passport_detail(request, public_id):
    event = current_event()
    raw = normalize_public_id(public_id)
    if not event or not raw:
        return render(request, "passport/unavailable.html", status=404)
    p = get_object_or_404(with_progress(Passport.objects.filter(event=event)), public_id=raw)
    stands = list(event.stands.filter(active=True))
    stamped_at = dict(p.stamps.values_list("stand_id", "created_at"))
    required_total = sum(1 for s in stands if s.required)
    audit(request.user, "passport.view", p.public_id)
    return render(request, "passport/staff_passport.html", {
        "p": p, "contact": mask_contact(p.contact), "status": prize_status(p, required_total),
        "rows": [{"stand": s, "area": area_key(s), "visited": s.pk in stamped_at, "stamped_at": stamped_at.get(s.pk)} for s in stands],
        "total": len(stands), "required_total": required_total, "prize_allowed": prize_allowed(request.user),
        "next_stamp_at": next_stamp_at(p),
    })


@never_cache
@manager_only
def manager_home(request):
    event = current_event()
    if not event:
        return render(request, "passport/manager.html", {"event": None})
    divisible = event.gap_seconds % 60 == 0
    form = IntervalForm(request.POST or None, initial={"minutes": event.gap_seconds // 60} if divisible else None)
    if request.method == "POST" and form.is_valid():
        old, new = set_gap_minutes(event.pk, form.cleaned_data["minutes"], request.user)
        if old == new:
            messages.info(request, "O intervalo já era esse. Nada foi alterado.")
        else:
            messages.success(request, f"Intervalo alterado de {interval_label(old) or 'nenhum'} para {interval_label(new)}. "
                                      "A mudança já vale para quem está aguardando o próximo carimbo.")
        return redirect("manager_home")
    now = timezone.now()
    waiting = Passport.objects.filter(event=event, last_stamp_at__gt=now - timedelta(seconds=event.gap_seconds)).count() if event.gap_seconds else 0
    stands = list(event.stands.filter(active=True))
    unmatched = [s for s in stands if not area_key(s)]
    return render(request, "passport/manager.html", {
        "event": event, "form": form, "gap": interval_label(event.gap_seconds), "divisible": divisible,
        "waiting": waiting, "stands": stands, "unmatched": unmatched,
        "required_total": sum(1 for s in stands if s.required),
    })


@never_cache
@manager_only
@require_safe
def manager_report(request):
    event = current_event()
    if not event:
        return render(request, "passport/manager_report.html", {"event": None}, status=503)

    stands = list(event.stands.annotate(
        visits=Count("stamps", filter=Q(stamps__passport__event=event)),
    ))
    required = [stand.pk for stand in stands if stand.active and stand.required]
    passports = Passport.objects.filter(event=event).annotate(
        completed_stands=Count("stamps", filter=Q(stamps__stand_id__in=required)),
        event_visits=Count("stamps", filter=Q(stamps__stand__event=event)),
    )
    completed = Q(completed_stands=len(required)) if required else Q(pk__in=[])
    totals = passports.aggregate(
        issued=Count("pk"),
        visited=Count("pk", filter=Q(event_visits__gt=0)),
        completed=Count("pk", filter=completed),
        eligible=Count("pk", filter=completed & Q(redemption__isnull=True)),
        redeemed=Count("pk", filter=Q(redemption__isnull=False)),
    )
    metrics = [
        ("Passaportes emitidos", totals["issued"]),
        ("Visitantes com pelo menos um carimbo", totals["visited"]),
        ("Circuitos concluídos", totals["completed"]),
        ("Aptos à retirada", totals["eligible"]),
        ("Prêmios entregues", totals["redeemed"]),
    ]
    if request.GET.get("formato") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="relatorio-circuito.csv"'
        response.write("\ufeff")
        writer = csv.writer(response, delimiter=";")
        writer.writerow(["Seção", "Indicador", "Total"])
        writer.writerows(("Resumo", label, total) for label, total in metrics)
        for stand in stands:
            name = stand.name
            if name.lstrip().startswith(("=", "+", "-", "@")) or name.startswith(("\t", "\r", "\n")):
                name = "'" + name
            writer.writerow(["Estandes", name, stand.visits])
        return response
    return render(request, "passport/manager_report.html", {
        "event": event, "metrics": metrics, "stands": stands,
    })
