from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import Group, User
from django.db import close_old_connections, connection
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from passport.models import Event, Passport, Redemption, Stand, Stamp
from passport.services import (
    CONSENT_VERSION, digest, eligible, find_ticket, issue_ticket, record_stamp,
    redeem, station_code, valid_station_code,
)
from passport.views import next_stamp_at

FAST_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class PassportTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(name="Teste", slug="teste", active=True)
        self.a = Stand.objects.create(event=self.event, name="Área A", position=1)
        self.b = Stand.objects.create(event=self.event, name="Área B", position=2)

    def make_passport(self, contact="pessoa@example.com"):
        return Passport.objects.create(
            event=self.event, name="Pessoa Teste", contact=contact,
            contact_digest=digest("contact", contact), pin_hash=make_password("123456"),
            consent_version=CONSENT_VERSION, consent_recorded_at=timezone.now(),
        )

    def in_session(self, client, p):
        session = client.session
        session["passport_id"] = p.pk
        session["passport_version"] = p.session_version
        session.save()

    def test_secure_same_origin_post_with_csrf(self):
        client = Client(enforce_csrf_checks=True)
        response = client.get(reverse("register"), secure=True)
        self.assertEqual(response["Referrer-Policy"], "same-origin")
        token = client.cookies["csrftoken"].value
        response = client.post(reverse("register"), {
            "name": "Pessoa", "contact": "85999998880", "pin": "123456",
            "pin_confirm": "123456", "csrfmiddlewaretoken": token,
        }, secure=True, HTTP_ORIGIN="https://testserver")
        self.assertEqual(response.status_code, 302)

    def test_registration_hashes_pin_and_consent_is_opt_in(self):
        response = self.client.post(reverse("register"), {
            "name": "Pessoa", "contact": "+55 (85) 99999-8888", "pin": "123456", "pin_confirm": "123456",
        })
        self.assertRedirects(response, reverse("passport"))
        p = Passport.objects.get()
        self.assertEqual(p.contact, "85999998888")
        self.assertFalse(p.consent_marketing)
        self.assertEqual(p.consent_version, "marketing-v2-celular-provisoria")
        self.assertNotEqual(p.pin_hash, "123456")
        self.assertTrue(check_password("123456", p.pin_hash))
        self.assertIsNotNone(p.consent_recorded_at)

    def test_marketing_consent_is_recorded(self):
        self.client.post(reverse("register"), {
            "name": "Pessoa", "contact": "85999998888", "pin": "123456",
            "pin_confirm": "123456", "marketing": "on",
        })
        self.assertTrue(Passport.objects.get().consent_marketing)

    def test_duplicate_contact_does_not_create_another_passport(self):
        self.make_passport("5585999998888")
        response = self.client.post(reverse("register"), {
            "name": "Outra", "contact": "(85) 99999-8888", "pin": "123456", "pin_confirm": "123456",
        })
        self.assertContains(response, "Não foi possível cadastrar")
        self.assertEqual(Passport.objects.count(), 1)

    def test_registration_rejects_email_and_non_mobile_contact(self):
        for contact in ("pessoa@example.com", "8532221234", "00 90000-0001"):
            response = self.client.post(reverse("register"), {
                "name": "Pessoa", "contact": contact, "pin": "123456", "pin_confirm": "123456",
            })
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors)
        self.assertEqual(Passport.objects.count(), 0)

    def test_recovery_accepts_legacy_country_code_without_changing_record(self):
        p = self.make_passport("5585999998888")
        response = self.client.post(reverse("recover"), {"contact": "(85) 99999-8888", "pin": "123456"})
        self.assertRedirects(response, reverse("passport"))
        p.refresh_from_db()
        self.assertEqual(p.contact, "5585999998888")

    def test_consent_checkbox_precedes_its_label_and_is_optional(self):
        response = self.client.get(reverse("register"))
        html = response.content.decode()
        self.assertContains(response, "Celular com DDD")
        self.assertNotContains(response, "E-mail ou telefone")
        self.assertLess(html.index('name="marketing"'), html.index('for="id_marketing"'))
        self.assertFalse(response.context["form"].fields["marketing"].required)

    def test_recovery_invalidates_previous_participant_session(self):
        p = self.make_passport()
        old = Client()
        self.in_session(old, p)
        new = Client()
        r = new.post(reverse("recover"), {"contact": p.contact, "pin": "123456"})
        self.assertRedirects(r, reverse("passport"))
        self.assertRedirects(old.get(reverse("passport")), reverse("recover"))
        self.assertEqual(new.get(reverse("passport")).status_code, 200)

    def test_recovery_has_account_rate_limit(self):
        p = self.make_passport()
        for _ in range(5):
            self.client.post(reverse("recover"), {"contact": p.contact, "pin": "000000"})
        response = self.client.post(reverse("recover"), {"contact": p.contact, "pin": "123456"})
        self.assertContains(response, "Não foi possível entrar")
        p.refresh_from_db()
        self.assertEqual(p.session_version, 1)

    def test_contact_wrong_pin_and_absent_account_get_same_message(self):
        p = self.make_passport()
        for contact in (p.contact, "outra@example.com"):
            response = self.client.post(reverse("recover"), {"contact": contact, "pin": "000000"})
            self.assertContains(response, "Não foi possível entrar")

    def test_cooldown_duplicate_and_failed_attempt_do_not_reset_clock(self):
        p = self.make_passport()
        start = timezone.now()
        self.assertEqual(record_stamp(p.pk, 1, self.a.pk, station_code(self.a, start), start)[0], "ok")
        t = start + timedelta(seconds=10)
        self.assertEqual(record_stamp(p.pk, 1, self.a.pk, station_code(self.a, t), t)[0], "duplicate")
        self.assertEqual(record_stamp(p.pk, 1, self.b.pk, "not-a-code", t)[0], "invalid")
        t = start + timedelta(seconds=299)
        self.assertEqual(record_stamp(p.pk, 1, self.b.pk, station_code(self.b, t), t), ("wait", 1))
        t = start + timedelta(seconds=300)
        self.assertEqual(record_stamp(p.pk, 1, self.b.pk, station_code(self.b, t), t)[0], "ok")
        self.assertEqual(Stamp.objects.count(), 2)

    def test_old_station_code_expires_and_current_is_shared(self):
        start = timezone.now().replace(second=5, microsecond=0)
        code = station_code(self.a, start)
        self.assertTrue(valid_station_code(self.a, code, start + timedelta(seconds=60)))
        self.assertFalse(valid_station_code(self.a, code, start + timedelta(seconds=120)))
        first = self.make_passport()
        second = self.make_passport("outro@example.com")
        self.assertEqual(record_stamp(first.pk, 1, self.a.pk, code, start)[0], "ok")
        self.assertEqual(record_stamp(second.pk, 1, self.a.pk, code, start)[0], "ok")

    def test_scan_get_does_not_write_and_post_requires_csrf(self):
        p = self.make_passport()
        client = Client(enforce_csrf_checks=True)
        self.in_session(client, p)
        url = reverse("scan_stamp", args=[self.a.pk, station_code(self.a)])
        self.assertEqual(client.get(url).status_code, 200)
        self.assertEqual(Stamp.objects.count(), 0)
        self.assertEqual(client.post(url).status_code, 403)
        token = client.cookies["csrftoken"].value
        self.assertEqual(client.post(url, {"csrfmiddlewaretoken": token}).status_code, 302)
        self.assertEqual(Stamp.objects.count(), 1)

    def test_scan_without_session_offers_registration_and_resumes_visit(self):
        url = reverse("scan_stamp", args=[self.a.pk, station_code(self.a)])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visita a Área A")
        self.assertContains(response, reverse("register"))
        self.assertContains(response, reverse("recover"))
        self.assertContains(self.client.get(reverse("register")), "você confirma a visita a <strong>Área A</strong>")
        response = self.client.post(reverse("register"), {
            "name": "Pessoa", "contact": "85999998888", "pin": "123456", "pin_confirm": "123456",
        })
        self.assertRedirects(response, url)
        self.assertContains(self.client.get(url), "Confirmar carimbo")
        self.assertEqual(Stamp.objects.count(), 0)

    def test_scan_without_session_for_unknown_stand_is_unavailable(self):
        url = reverse("scan_stamp", args=[self.a.pk + 100, station_code(self.a)])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertNotIn("pending_scan", self.client.session)

    def test_expired_scan_code_asks_to_read_qr_again(self):
        p = self.make_passport()
        self.in_session(self.client, p)
        old = station_code(self.a, timezone.now() - timedelta(seconds=180))
        url = reverse("scan_stamp", args=[self.a.pk, old])
        response = self.client.get(url)
        self.assertContains(response, "Ler o QR novamente")
        self.assertNotContains(response, "Confirmar carimbo")
        self.assertRedirects(self.client.post(url), reverse("manual_stamp") + "#leitor", fetch_redirect_response=False)
        self.assertEqual(Stamp.objects.count(), 0)

    def test_passport_shows_when_next_stamp_is_allowed(self):
        p = self.make_passport()
        self.in_session(self.client, p)
        self.assertNotContains(self.client.get(reverse("passport")), "próximo carimbo fica disponível")
        now = timezone.now().replace(second=20, microsecond=0)
        self.assertEqual(record_stamp(p.pk, 1, self.a.pk, station_code(self.a, now), now)[0], "ok")
        p.refresh_from_db()
        # 20 s após o minuto + 300 s: exibir o minuto seguinte, nunca um horário ainda bloqueado.
        shown = timezone.localtime(now + timedelta(seconds=340)).strftime("%H:%M")
        self.assertEqual(timezone.localtime(next_stamp_at(p, now)).strftime("%H:%M"), shown)
        self.assertIsNone(next_stamp_at(p, now + timedelta(seconds=300)))
        Passport.objects.filter(pk=p.pk).update(last_stamp_at=timezone.now() - timedelta(seconds=10))
        response = self.client.get(reverse("passport"))
        self.assertContains(response, "próximo carimbo fica disponível")
        self.assertContains(self.client.get(reverse("manual_stamp")), "próximo carimbo fica disponível")
        Passport.objects.filter(pk=p.pk).update(last_stamp_at=timezone.now() - timedelta(seconds=301))
        self.assertNotContains(self.client.get(reverse("passport")), "próximo carimbo fica disponível")

    def test_interval_text_follows_event_configuration(self):
        p = self.make_passport()
        self.in_session(self.client, p)
        self.assertContains(self.client.get(reverse("home")), "aguarde 5 minutos entre registros")
        self.assertContains(self.client.get(reverse("passport")), "Aguarde 5 minutos entre carimbos")
        Event.objects.filter(pk=self.event.pk).update(gap_seconds=90)
        self.assertContains(self.client.get(reverse("passport")), "Aguarde 1 minuto e 30 s entre carimbos")
        Event.objects.filter(pk=self.event.pk).update(gap_seconds=0)
        self.assertNotContains(self.client.get(reverse("passport")), "entre carimbos")
        self.assertContains(self.client.get(reverse("home")), "Acompanhe seu progresso.")

    def test_passport_counter_keeps_space_when_line_break_is_hidden(self):
        p = self.make_passport()
        self.in_session(self.client, p)
        self.assertContains(self.client.get(reverse("passport")), "carimbos <br>registrados")

    def test_stamp_feedback_names_stand_and_highlights_it_once(self):
        p = self.make_passport()
        self.in_session(self.client, p)
        url = reverse("scan_stamp", args=[self.a.pk, station_code(self.a)])
        response = self.client.post(url, follow=True)
        stamp = Stamp.objects.get()
        shown = timezone.localtime(stamp.created_at).strftime("%H:%M")
        self.assertContains(response, f"Área A carimbado às {shown}.")
        self.assertContains(response, "just-stamped", count=1)
        self.assertContains(response, f"Carimbado às <time datetime=")
        self.assertNotContains(self.client.get(reverse("passport")), "just-stamped")

    def test_reward_moves_to_top_only_while_it_can_be_claimed(self):
        p = self.make_passport()
        self.in_session(self.client, p)
        html = self.client.get(reverse("passport")).content.decode()
        self.assertLess(html.index('id="next-step"'), html.index('id="premio"'))
        self.complete(p)
        html = self.client.get(reverse("passport")).content.decode()
        self.assertLess(html.index('id="premio"'), html.index('id="next-step"'))
        self.assertIn("reward-first", html)
        Redemption.objects.create(passport=p, staff=User.objects.create_user("prize", is_staff=True))
        html = self.client.get(reverse("passport")).content.decode()
        self.assertLess(html.index('id="next-step"'), html.index('id="premio"'))

    def test_sign_in_has_one_name_and_no_external_link_icon(self):
        p = self.make_passport()
        scan = reverse("scan_stamp", args=[self.a.pk, station_code(self.a)])
        for url in (reverse("home"), reverse("register"), reverse("recover"), scan):
            response = self.client.get(url)
            self.assertContains(response, "Entrar no passaporte")
            for old in ("Já tenho acesso", "Recuperar acesso", "Recupere seu acesso", "Já tenho passaporte"):
                self.assertNotContains(response, old)
        self.in_session(self.client, p)
        for url in (reverse("passport"), reverse("manual_stamp")):
            self.assertNotContains(self.client.get(url), "M7 17 17 7")

    def test_register_visit_offers_camera_and_manual_fallback(self):
        p = self.make_passport()
        self.in_session(self.client, p)
        response = self.client.get(reverse("manual_stamp"))
        self.assertContains(response, "Escanear QR code")
        self.assertContains(response, "Digitar código")
        self.assertContains(response, "data-qr-scanner")
        self.assertContains(response, "passport/scanner.js")

    def test_unassigned_staff_cannot_access_station(self):
        user = User.objects.create_user("staff", password="secret", is_staff=True)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("station", args=[self.a.pk])).status_code, 403)
        self.a.staff.add(user)
        response = self.client.get(reverse("station", args=[self.a.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data:image/svg+xml;base64,")

    def test_empty_required_set_is_not_eligible(self):
        p = self.make_passport()
        Stand.objects.update(required=False)
        self.assertFalse(eligible(p))
        self.assertIsNone(issue_ticket(p.pk, p.session_version))

    def complete(self, p):
        start = timezone.now()
        for stand, when in ((self.a, start), (self.b, start + timedelta(seconds=300))):
            self.assertEqual(record_stamp(p.pk, p.session_version, stand.pk, station_code(stand, when), when)[0], "ok")

    def test_prize_is_staff_only_and_confirmation_is_idempotent(self):
        p = self.make_passport()
        self.complete(p)
        code = issue_ticket(p.pk, 1)
        self.assertIsNotNone(find_ticket(code))
        staff = User.objects.create_user("prize", password="secret", is_staff=True)
        group = Group.objects.create(name="Premiação")
        staff.groups.add(group)
        self.client.force_login(staff)
        url = reverse("prize_review", args=[code])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(Redemption.objects.count(), 0)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(Redemption.objects.count(), 1)
        self.assertEqual(Redemption.objects.get().staff, staff)
        self.assertIsNone(issue_ticket(p.pk, 1))

    def test_prize_permission_is_separate_from_station_permission(self):
        p = self.make_passport()
        self.complete(p)
        code = issue_ticket(p.pk, 1)
        staff = User.objects.create_user("station", password="secret", is_staff=True)
        self.a.staff.add(staff)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("prize_review", args=[code])).status_code, 403)

    def test_regenerated_ticket_invalidates_previous_one(self):
        p = self.make_passport()
        self.complete(p)
        first = issue_ticket(p.pk, 1)
        second = issue_ticket(p.pk, 1)
        self.assertNotEqual(first, second)
        self.assertIsNone(find_ticket(first))
        self.assertIsNotNone(find_ticket(second))

    def test_expired_ticket_cannot_be_redeemed(self):
        p = self.make_passport()
        self.complete(p)
        code = issue_ticket(p.pk, 1)
        ticket = p.ticket
        ticket.expires_at = timezone.now() - timedelta(seconds=1)
        ticket.save(update_fields=["expires_at"])
        staff = User.objects.create_user("prize", is_staff=True)
        self.assertEqual(redeem(code, staff), "invalid")
        self.assertEqual(Redemption.objects.count(), 0)


@skipUnless(connection.vendor == "postgresql", "O teste de concorrência exige PostgreSQL.")
@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class ConcurrentStampTests(TransactionTestCase):
    def test_simultaneous_different_stands_only_one_stamp(self):
        event = Event.objects.create(name="Teste", slug="teste", active=True)
        a = Stand.objects.create(event=event, name="A")
        b = Stand.objects.create(event=event, name="B")
        p = Passport.objects.create(
            event=event, name="Teste", contact="x@example.com", contact_digest=digest("contact", "x@example.com"),
            pin_hash=make_password("123456"), consent_version=CONSENT_VERSION,
            consent_recorded_at=timezone.now(),
        )
        now = timezone.now()
        barrier = Barrier(2)

        def attempt(stand):
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                return record_stamp(p.pk, 1, stand.pk, station_code(stand, now), now)[0]
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, (a, b)))
        self.assertCountEqual(results, ["ok", "wait"])
        self.assertEqual(Stamp.objects.count(), 1)
