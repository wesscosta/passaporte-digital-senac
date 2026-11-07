"""Exportações restritas à gestão; nunca incluem credenciais."""
import csv
from django.http import HttpResponse
from django.utils import timezone
from .models import Passport, Stamp
from .services import audit

def cell(value):
    text = "" if value is None else str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text

def date(value):
    return timezone.localtime(value).isoformat(timespec="seconds") if value else ""

def detailed_report(request, event, kind):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{kind}-{event.pk}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    generated = date(timezone.now())
    prefix = [event.name, generated]
    count = 0
    if kind == "participantes":
        writer.writerow(["Evento", "Gerado em", "Identificador", "Nome", "Celular/contato",
            "Cadastro", "Interesse", "Autoriza novidades", "Versão novidades", "Registro novidades",
            "Autoriza imagem", "Versão imagem", "Registro imagem", "Carimbos",
            "Situação do prêmio", "Retirada em"])
        required = set(event.stands.filter(active=True, required=True).values_list("pk", flat=True))
        rows = Passport.objects.filter(event=event).select_related("redemption").prefetch_related("stamps").order_by("pk")
        for p in rows.iterator(chunk_size=500):
            stamps = [s for s in p.stamps.all()]
            redemption = getattr(p, "redemption", None)
            status = "Entregue" if redemption else ("Apto" if required and required.issubset({s.stand_id for s in stamps}) else "Não apto")
            writer.writerow(map(cell, prefix + [p.display_id, p.name, p.contact, date(p.created_at),
                p.get_interest_segment_display(), "Sim" if p.consent_marketing else "Não",
                p.consent_version, date(p.consent_recorded_at),
                "Não informado" if p.consent_image is None else ("Sim" if p.consent_image else "Não"),
                p.consent_image_version, date(p.consent_image_recorded_at), len(stamps), status,
                date(redemption.created_at) if redemption else ""]))
            count += 1
    else:
        writer.writerow(["Evento", "Gerado em", "Identificador", "Estande", "Carimbo em"])
        for s in Stamp.objects.filter(passport__event=event, stand__event=event).select_related("passport", "stand").order_by("pk").iterator(chunk_size=500):
            writer.writerow(map(cell, prefix + [s.passport.display_id, s.stand.name, date(s.created_at)]))
            count += 1
    audit(request.user, "report.export", str(event.pk), formato=kind, registros=count)
    return response
