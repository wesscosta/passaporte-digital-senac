from django.contrib import admin
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from passport.models import Event, InterestSegment, Passport
from passport.services import IMAGE_CONSENT_VERSION


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RegistrationDetailsTests(TestCase):
    def setUp(self):
        Event.objects.create(name="Evento de teste", slug="teste", active=True)

    def fields(self, **overrides):
        fields = {
            "name": "Pessoa Fictícia",
            "contact": "10900000001",
            "interest_segment": InterestSegment.TECNOLOGIA,
            "pin": "246810",
            "pin_confirm": "246810",
        }
        return {**fields, **overrides}

    def test_segment_is_required_and_rejects_unknown_value(self):
        for segment in ("", "nao_existe"):
            with self.subTest(segment=segment):
                response = self.client.post(reverse("register"), self.fields(interest_segment=segment))
                self.assertEqual(response.status_code, 200)
                self.assertIn("interest_segment", response.context["form"].errors)
        self.assertFalse(Passport.objects.exists())

    def test_independent_optional_choices_are_recorded(self):
        for number, image, marketing in (
            (1, False, False), (2, True, False), (3, False, True), (4, True, True),
        ):
            with self.subTest(image=image, marketing=marketing):
                fields = self.fields(contact=f"1090000000{number}")
                if image:
                    fields["image_consent"] = "on"
                if marketing:
                    fields["marketing"] = "on"
                response = Client().post(reverse("register"), fields)
                self.assertEqual(response.status_code, 302)
                passport = Passport.objects.get(contact=fields["contact"])
                self.assertEqual(passport.interest_segment, InterestSegment.TECNOLOGIA)
                self.assertIs(passport.consent_image, image)
                self.assertIs(passport.consent_marketing, marketing)
                self.assertEqual(passport.consent_image_version, IMAGE_CONSENT_VERSION)
                self.assertIsNotNone(passport.consent_image_recorded_at)
                self.assertEqual(passport.consent_image_recorded_at, passport.consent_recorded_at)

    def test_form_explains_choices_and_does_not_precheck_or_require_them(self):
        response = self.client.get(reverse("register"))
        form = response.context["form"]
        html = response.content.decode()
        self.assertTrue(form.fields["interest_segment"].required)
        self.assertFalse(form.fields["image_consent"].required)
        self.assertFalse(form.fields["marketing"].required)
        self.assertContains(response, "Nome completo")
        self.assertContains(response, "Autorizações opcionais")
        self.assertContains(response, "Nenhuma delas é necessária para participar")
        self.assertContains(response, "Ambiente de teste: não informe dados reais")
        for name in ("image_consent", "marketing"):
            rendered = str(form[name])
            self.assertNotIn("checked", rendered)
            self.assertNotIn("required", rendered)
            self.assertLess(html.index(f'name="{name}"'), html.index(f'for="id_{name}"'))
        self.assertIn('id="id_contact_helptext"', html)
        self.assertIn("Celular/WhatsApp com DDD", html)
        self.assertIn('data-phone-mask="br-mobile"', html)
        self.assertIn("phone-mask.js", html)

    def test_form_preserves_selection_when_other_field_is_invalid(self):
        response = self.client.post(reverse("register"), self.fields(
            interest_segment=InterestSegment.GESTAO, image_consent="on", pin_confirm="000000",
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"]["interest_segment"].value(), InterestSegment.GESTAO)
        self.assertTrue(response.context["form"]["image_consent"].value())
        self.assertIn("pin_confirm", response.context["form"].errors)
        self.assertFalse(Passport.objects.exists())

    def test_admin_displays_new_values_as_readonly(self):
        passport_admin = admin.site._registry[Passport]
        for name in ("interest_segment", "consent_image", "consent_image_version", "consent_image_recorded_at"):
            self.assertIn(name, passport_admin.readonly_fields)
        self.assertIn("interest_segment", passport_admin.list_display)
        self.assertIn("consent_image", passport_admin.list_display)


class ExistingPassportMigrationTests(TransactionTestCase):
    def test_old_records_are_preserved_and_image_choice_is_unknown(self):
        executor = MigrationExecutor(connection)
        old_target = [("passport", "0002_public_id_manager_audit")]
        try:
            executor.migrate(old_target)
            old_apps = executor.loader.project_state(old_target).apps
            OldEvent = old_apps.get_model("passport", "Event")
            OldPassport = old_apps.get_model("passport", "Passport")
            event = OldEvent.objects.create(name="Evento legado", slug="legado", active=True)
            timestamp = timezone.now()
            previous = OldPassport.objects.create(
                event=event, public_id="ABCD2345", name="Registro fictício", contact="10900000003",
                contact_digest="digest-ficticio", pin_hash="hash-ficticio", session_version=3,
                consent_marketing=True, consent_version="marketing-antigo", consent_recorded_at=timestamp,
            )
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
            passport = Passport.objects.get(pk=previous.pk)
            self.assertEqual(passport.name, "Registro fictício")
            self.assertEqual(passport.contact, "10900000003")
            self.assertEqual(passport.public_id, "ABCD2345")
            self.assertEqual(passport.session_version, 3)
            self.assertTrue(passport.consent_marketing)
            self.assertEqual(passport.consent_version, "marketing-antigo")
            self.assertEqual(passport.consent_recorded_at, timestamp)
            self.assertEqual(passport.interest_segment, "")
            self.assertIsNone(passport.consent_image)
            self.assertEqual(passport.consent_image_version, "")
            self.assertIsNone(passport.consent_image_recorded_at)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
