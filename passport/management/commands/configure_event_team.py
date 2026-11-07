"""Configura contas operacionais explícitas, sem conceder superusuário."""
import secrets
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from passport.models import Event
from passport.services import audit

class Command(BaseCommand):
    help = "Configura staff_local, premiacao_suporte e gestor_local; mostra senhas novas uma vez."
    def add_arguments(self, parser):
        parser.add_argument("--reset-passwords", action="store_true")
    @transaction.atomic
    def handle(self, *args, **options):
        events = list(Event.objects.filter(active=True))
        if len(events) != 1:
            raise CommandError("Exige exatamente um evento ativo.")
        User = get_user_model()
        names = ["staff_local", "premiacao_suporte", "gestor_local"]
        if User.objects.filter(username__in=names, is_superuser=True).exists():
            raise CommandError("Uma conta operacional é superusuária. Revise antes de alterar seus acessos.")
        manage = Permission.objects.get(content_type__app_label="passport", content_type__model="event", codename="manage_event")
        reset = Permission.objects.get(content_type__app_label="passport", content_type__model="event", codename="reset_pin")
        prize, _ = Group.objects.get_or_create(name="Premiação")
        # Evita herdar privilégios inesperados de um grupo existente.
        if prize.permissions.exists():
            raise CommandError("Grupo Premiação tem permissões adicionais; revise antes de continuar.")
        credentials = []
        for name in names:
            user, created = User.objects.get_or_create(username=name)
            user.is_active = user.is_staff = True
            if created or options["reset_passwords"]:
                password = secrets.token_urlsafe(18)
                user.set_password(password)
                credentials.append((name, password))
            user.save()
            user.groups.set([prize] if name == "premiacao_suporte" else [])
            user.user_permissions.set([manage] if name == "gestor_local" else [reset] if name == "premiacao_suporte" else [])
            user.assigned_stands.set(events[0].stands.filter(active=True) if name == "staff_local" else [])
            audit(user, "team.configure", str(user.pk), perfil=name, origem="comando_administrativo")
        for name, password in credentials:
            self.stdout.write(f"{name}: {password}")
        self.stdout.write("Perfis configurados. Senhas existentes preservadas, salvo --reset-passwords.")
