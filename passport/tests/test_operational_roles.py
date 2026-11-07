import csv
import io
from django.test import TestCase
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from passport.models import Event, Stand, Passport, Stamp, AuditEntry
from passport.permissions import prize_allowed, can_reset_pin, is_manager

class OperationalRolesTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(name="Evento sintético", slug="teste", active=True)
        self.stand = Stand.objects.create(event=self.event, name="Área", required=True)
        self.output = io.StringIO()
        call_command("configure_event_team", stdout=self.output)
    def test_roles_and_password_preservation(self):
        users = get_user_model().objects
        staff = users.get(username="staff_local")
        prize = users.get(username="premiacao_suporte")
        manager = users.get(username="gestor_local")
        self.assertFalse(prize_allowed(staff))
        self.assertFalse(can_reset_pin(staff))
        self.assertTrue(staff.assigned_stands.filter(pk=self.stand.pk).exists())
        self.assertTrue(prize_allowed(prize))
        self.assertTrue(can_reset_pin(prize))
        self.assertFalse(is_manager(prize))
        self.assertTrue(is_manager(manager))
        self.assertFalse(manager.is_superuser)
        password = staff.password
        out = io.StringIO()
        call_command("configure_event_team", stdout=out)
        staff.refresh_from_db()
        self.assertEqual(staff.password, password)
        self.assertNotIn("staff_local:", out.getvalue())
    def test_export_scope_fields_and_permissions(self):
        p = Passport.objects.create(event=self.event, name="=SINTETICO", contact="+5585999990000",
            contact_digest="synthetic", pin_hash="SECRET_NOT_EXPORTED", consent_version="test",
            consent_recorded_at=timezone.now())
        Stamp.objects.create(passport=p, stand=self.stand, created_at=timezone.now())
        other = Event.objects.create(name="Outro", slug="outro")
        Passport.objects.create(event=other, name="OUTRO_EVENTO", contact="000", contact_digest="other",
            pin_hash="secret", consent_version="test", consent_recorded_at=timezone.now())
        url = reverse("manager_report")
        for name in ("staff_local", "premiacao_suporte"):
            self.client.force_login(get_user_model().objects.get(username=name))
            self.assertEqual(self.client.get(url, {"formato":"participantes"}).status_code, 403)
        self.client.force_login(get_user_model().objects.get(username="gestor_local"))
        for kind in ("participantes", "visitas"):
            r = self.client.get(url, {"formato":kind})
            self.assertEqual(r.status_code, 200)
            self.assertIn("no-store", r["Cache-Control"])
            text = r.content.decode("utf-8-sig")
            self.assertNotIn("SECRET_NOT_EXPORTED", text)
            self.assertNotIn("OUTRO_EVENTO", text)
            rows = list(csv.reader(io.StringIO(text), delimiter=";"))
            self.assertEqual(len(rows), 2)
            self.assertEqual(len(rows[0]), len(rows[1]))
            self.assertIn(p.display_id, rows[1])
            if kind == "participantes":
                self.assertIn("'=SINTETICO", rows[1])
                self.assertIn("'+5585999990000", rows[1])
                self.assertIn("Apto", rows[1])
        self.assertEqual(AuditEntry.objects.filter(action="report.export").count(), 2)
