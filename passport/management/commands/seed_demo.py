from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from passport.models import Event, Stand

AREAS = [
    "Tecnologia da Informação", "Artes e Design", "Gastronomia e Turismo",
    "Moda e Beleza", "Gestão e Comércio", "Saúde",
]


class Command(BaseCommand):
    help = "Cria evento e seis estandes DEMONSTRATIVOS, sem participantes ou usuários."

    @transaction.atomic
    def handle(self, *args, **options):
        if Event.objects.filter(active=True).exclude(slug="circuito-senac-demo").exists():
            raise CommandError("Já existe outro evento ativo; nenhuma alteração foi feita.")
        event, created = Event.objects.get_or_create(
            slug="circuito-senac-demo",
            defaults={"name": "Circuito Senac — demonstração", "active": True, "gap_seconds": 300},
        )
        if not created:
            self.stdout.write("Evento de demonstração já existe; sem alterações.")
            return
        for i, name in enumerate(AREAS, start=1):
            Stand.objects.create(event=event, name=name, position=i, required=True)
        Group.objects.get_or_create(name="Premiação")
        self.stdout.write(self.style.SUCCESS("Evento demonstrativo criado: 6 estandes provisórios."))
