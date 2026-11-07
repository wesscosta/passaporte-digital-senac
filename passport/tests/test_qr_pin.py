"""A3 (comprovante de leitura do QR durante cadastro/entrada) e A4 (redefinição de PIN pela equipe). Dados sintéticos."""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import Group, Permission, User
from django.db import close_old_connections, connection
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from passport.models import AuditEntry, Event, Passport, ScanVoucher, Stamp, Stand
from passport.services import (
    CONSENT_VERSION, digest, issue_scan_voucher, record_stamp_with_voucher, reset_visitor_pin, station_code,
)
from passport.views import VOUCHER_SESSION_KEY

FAST_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def make_passport(event, contact="85999990000", name="Pessoa Sintética", pin="123456"):
    return Passport.objects.create(
        event=event, name=name, contact=contact, contact_digest=digest("contact", contact),
        pin_hash=make_password(pin), consent_version=CONSENT_VERSION, consent_recorded_at=timezone.now(),
    )


def sign_in(client, p):
    session = client.session
    session["passport_id"], session["passport_version"] = p.pk, p.session_version
    session.save()


REGISTER = {"name": "Pessoa Nova", "contact": "85988887777", "pin": "246813", "pin_confirm": "246813",
            "interest_segment": "saude"}


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class ScanVoucherTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(name="Teste", slug="teste", active=True)
        self.a = Stand.objects.create(event=self.event, name="Área A", position=1)
        self.b = Stand.objects.create(event=self.event, name="Área B", position=2)

    def scan(self, stand=None, code=None, client=None):
        stand = stand or self.a
        return (client or self.client).get(reverse("scan_stamp", args=[stand.pk, code or station_code(stand)]))

    def age_voucher(self, seconds_left):
        """Simula o tempo de cadastro: o código do QR já venceu, o comprovante ainda vale `seconds_left`."""
        now = timezone.now()
        ScanVoucher.objects.update(created_at=now - timedelta(seconds=300 - seconds_left),
                                   expires_at=now + timedelta(seconds=seconds_left))

    def test_invalid_or_expired_qr_does_not_create_voucher(self):
        old = station_code(self.a, timezone.now() - timedelta(seconds=180))
        response = self.scan(code=old)
        self.assertContains(response, "Este QR já mudou")
        wrong = f"{(int(station_code(self.a)) + 1) % 1_000_000:06d}"
        self.scan(code=wrong)
        self.assertFalse(ScanVoucher.objects.exists())
        self.assertNotIn(VOUCHER_SESSION_KEY, self.client.session)
        Stand.objects.filter(pk=self.a.pk).update(active=False)
        self.assertEqual(self.scan().status_code, 404)
        self.assertFalse(ScanVoucher.objects.exists())

    def test_valid_qr_creates_voucher_with_digest_only_in_database(self):
        response = self.scan()
        self.assertContains(response, "Sua leitura foi guardada")
        voucher = ScanVoucher.objects.get()
        token = self.client.session[VOUCHER_SESSION_KEY]
        self.assertNotEqual(voucher.token_digest, token)
        self.assertEqual(voucher.token_digest, digest("scan_voucher", token))
        self.assertEqual((voucher.expires_at - voucher.created_at).total_seconds(), 300)
        self.assertEqual((voucher.event_id, voucher.stand_id), (self.event.pk, self.a.pk))
        self.assertNotIn(token, response.content.decode())

    def test_registration_after_qr_code_changed_still_confirms_with_session_key_rotation(self):
        self.scan()
        self.age_voucher(60)
        key_before = self.client.session.session_key
        response = self.client.post(reverse("register"), REGISTER)
        self.assertRedirects(response, reverse("scan_voucher_confirm"))
        self.assertNotEqual(self.client.session.session_key, key_before)
        self.assertIn(VOUCHER_SESSION_KEY, self.client.session)
        page = self.client.get(reverse("scan_voucher_confirm"))
        self.assertContains(page, "Área A")
        self.assertContains(page, "A leitura do QR vale até")
        response = self.client.post(reverse("scan_voucher_confirm"), follow=True)
        self.assertContains(response, "Área A carimbado às")
        stamp = Stamp.objects.get()
        self.assertEqual(stamp.stand, self.a)
        voucher = ScanVoucher.objects.get()
        self.assertIsNotNone(voucher.consumed_at)
        self.assertEqual(voucher.consumed_by, stamp.passport)
        self.assertNotIn(VOUCHER_SESSION_KEY, self.client.session)

    def test_sign_in_with_pin_also_keeps_voucher(self):
        p = make_passport(self.event)
        self.scan()
        response = self.client.post(reverse("recover"), {"contact": p.contact, "pin": "123456"})
        self.assertRedirects(response, reverse("scan_voucher_confirm"))
        self.client.post(reverse("scan_voucher_confirm"))
        self.assertTrue(Stamp.objects.filter(passport=p, stand=self.a).exists())

    def test_expired_voucher_asks_for_new_reading(self):
        p = make_passport(self.event)
        self.scan()
        sign_in(self.client, p)
        ScanVoucher.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.client.get(reverse("scan_voucher_confirm"))
        self.assertContains(response, "A leitura do QR expirou", status_code=410)
        self.assertNotIn(VOUCHER_SESSION_KEY, self.client.session)
        # POST com o comprovante vencido também não carimba.
        self.scan(client=self.client)  # usuário logado: só mostra a confirmação normal, sem comprovante novo
        session = self.client.session
        token, voucher = issue_scan_voucher(self.a, station_code(self.a))
        session[VOUCHER_SESSION_KEY] = token
        session.save()
        ScanVoucher.objects.filter(pk=voucher.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.client.post(reverse("scan_voucher_confirm"))
        self.assertRedirects(response, reverse("manual_stamp") + "#leitor", fetch_redirect_response=False)
        self.assertFalse(Stamp.objects.exists())
        self.assertIsNone(ScanVoucher.objects.get(pk=voucher.pk).consumed_at)

    def test_voucher_is_single_use(self):
        p = make_passport(self.event)
        token, voucher = issue_scan_voucher(self.a, station_code(self.a))
        self.assertEqual(record_stamp_with_voucher(p.pk, 1, token)[0], "ok")
        self.assertEqual(record_stamp_with_voucher(p.pk, 1, token)[0], "used")
        other = make_passport(self.event, contact="85999990001")
        self.assertEqual(record_stamp_with_voucher(other.pk, 1, token)[0], "used")
        self.assertEqual(Stamp.objects.count(), 1)
        self.assertEqual(record_stamp_with_voucher(p.pk, 1, "token-inexistente")[0], "invalid")

    def test_wait_keeps_voucher_until_it_expires(self):
        p = make_passport(self.event)
        now = timezone.now()
        Stamp.objects.create(passport=p, stand=self.b, created_at=now - timedelta(seconds=30))
        Passport.objects.filter(pk=p.pk).update(last_stamp_at=now - timedelta(seconds=30))
        self.scan()
        sign_in(self.client, p)
        response = self.client.post(reverse("scan_voucher_confirm"), follow=True)
        self.assertContains(response, "Seu próximo carimbo fica disponível às")
        self.assertContains(response, "Visita pendente: Área A")
        self.assertIn(VOUCHER_SESSION_KEY, self.client.session)
        self.assertIsNone(ScanVoucher.objects.get().consumed_at)
        # Fim do intervalo antes do vencimento do comprovante: confirma sem nova leitura.
        Passport.objects.filter(pk=p.pk).update(last_stamp_at=now - timedelta(seconds=301))
        self.client.post(reverse("scan_voucher_confirm"))
        self.assertTrue(Stamp.objects.filter(passport=p, stand=self.a).exists())
        self.assertIsNotNone(ScanVoucher.objects.get().consumed_at)

    def test_duplicate_closes_voucher_without_new_stamp(self):
        p = make_passport(self.event)
        Stamp.objects.create(passport=p, stand=self.a, created_at=timezone.now() - timedelta(hours=1))
        token, _ = issue_scan_voucher(self.a, station_code(self.a))
        self.assertEqual(record_stamp_with_voucher(p.pk, 1, token)[0], "duplicate")
        self.assertIsNotNone(ScanVoucher.objects.get().consumed_at)
        self.assertEqual(Stamp.objects.count(), 1)

    def test_revalidates_event_stand_and_session_on_consumption(self):
        p = make_passport(self.event)
        token, _ = issue_scan_voucher(self.a, station_code(self.a))
        Event.objects.filter(pk=self.event.pk).update(active=False)
        self.assertEqual(record_stamp_with_voucher(p.pk, 1, token)[0], "invalid")
        Event.objects.filter(pk=self.event.pk).update(active=True)
        Stand.objects.filter(pk=self.a.pk).update(active=False)
        self.assertEqual(record_stamp_with_voucher(p.pk, 1, token)[0], "invalid")
        Stand.objects.filter(pk=self.a.pk).update(active=True)
        self.assertEqual(record_stamp_with_voucher(p.pk, 2, token)[0], "session")
        other_event = Event.objects.create(name="Outro", slug="outro", active=False)
        stranger = make_passport(other_event, contact="85999990002")
        self.assertEqual(record_stamp_with_voucher(stranger.pk, 1, token)[0], "invalid")
        self.assertFalse(Stamp.objects.exists())
        self.assertEqual(record_stamp_with_voucher(p.pk, 1, token)[0], "ok")

    def test_voucher_is_bound_to_the_session_that_scanned(self):
        p = make_passport(self.event)
        self.scan()
        other = Client()
        sign_in(other, p)
        self.assertRedirects(other.post(reverse("scan_voucher_confirm")), reverse("passport"), fetch_redirect_response=False)
        self.assertFalse(Stamp.objects.exists())

    def test_confirmation_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        p = make_passport(self.event)
        self.scan(client=client)
        sign_in(client, p)
        self.assertEqual(client.post(reverse("scan_voucher_confirm")).status_code, 403)
        self.assertFalse(Stamp.objects.exists())


@skipUnless(connection.vendor == "postgresql", "O teste de concorrência exige PostgreSQL.")
@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class ConcurrentVoucherTests(TransactionTestCase):
    def run_parallel(self, calls):
        barrier = Barrier(len(calls))

        def attempt(call):
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                return call()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(calls)) as pool:
            return list(pool.map(attempt, calls))

    def test_same_voucher_consumed_once_under_concurrency(self):
        event = Event.objects.create(name="Teste", slug="teste", active=True)
        stand = Stand.objects.create(event=event, name="A")
        first, second = make_passport(event), make_passport(event, contact="85999990003")
        token, _ = issue_scan_voucher(stand, station_code(stand))
        results = self.run_parallel([
            lambda: record_stamp_with_voucher(first.pk, 1, token)[0],
            lambda: record_stamp_with_voucher(second.pk, 1, token)[0],
            lambda: record_stamp_with_voucher(first.pk, 1, token)[0],
        ])
        self.assertEqual(results.count("ok"), 1)
        self.assertEqual(results.count("used"), 2)
        self.assertEqual(Stamp.objects.count(), 1)

    def test_vouchers_for_two_stands_respect_interval(self):
        event = Event.objects.create(name="Teste", slug="teste", active=True)
        a, b = Stand.objects.create(event=event, name="A"), Stand.objects.create(event=event, name="B")
        p = make_passport(event)
        token_a, _ = issue_scan_voucher(a, station_code(a))
        token_b, _ = issue_scan_voucher(b, station_code(b))
        results = self.run_parallel([
            lambda: record_stamp_with_voucher(p.pk, 1, token_a)[0],
            lambda: record_stamp_with_voucher(p.pk, 1, token_b)[0],
        ])
        self.assertCountEqual(results, ["ok", "wait"])
        self.assertEqual(Stamp.objects.count(), 1)
        self.assertEqual(ScanVoucher.objects.filter(consumed_at__isnull=True).count(), 1)

    def test_concurrent_pin_resets_generate_one_pin(self):
        event = Event.objects.create(name="Teste", slug="teste", active=True)
        p = make_passport(event)
        operator = User.objects.create_user("operador", is_staff=True)
        results = self.run_parallel([lambda: reset_visitor_pin(p.pk, event.pk, operator, "aparelho")[0]] * 3)
        self.assertEqual(results.count("ok"), 1)
        self.assertEqual(results.count("recent"), 2)
        p.refresh_from_db()
        self.assertEqual(p.session_version, 2)
        self.assertEqual(AuditEntry.objects.filter(action="visitor.pin_reset").count(), 1)


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class PinResetTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(name="Teste", slug="teste", active=True)
        Stand.objects.create(event=self.event, name="Área A")
        self.p = make_passport(self.event)
        self.reset_group = Group.objects.create(name="Redefinição de PIN")
        self.reset_group.permissions.add(Permission.objects.get(codename="reset_pin"))
        self.manager_group = Group.objects.create(name="Gestão")
        self.manager_group.permissions.add(Permission.objects.get(codename="manage_event"))

    def operator(self, name="operador", groups=(), is_staff=True):
        user = User.objects.create_user(name, is_staff=is_staff)
        for group in groups:
            user.groups.add(group)
        client = Client()
        client.force_login(user)
        return client, user

    def confirm_url(self, p=None):
        return reverse("pin_reset_confirm", args=[(p or self.p).display_id])

    def submit(self, client, data=None, p=None):
        page = client.get(self.confirm_url(p))
        nonce = re.search(r'name="nonce" value="([^"]+)"', page.content.decode()).group(1)
        payload = {"method": "aparelho", "confirmed": "on", "nonce": nonce}
        payload.update(data or {})
        return client.post(self.confirm_url(p), payload)

    def test_permission_is_explicit_and_not_implied_by_staff_or_manager(self):
        urls = (reverse("pin_reset_search"), self.confirm_url())
        self.assertEqual(Client().get(urls[0]).status_code, 302)
        for groups, is_staff, expected in (
            ((), True, 403),
            ((self.manager_group,), True, 403),
            ((self.reset_group,), False, 403),
            ((self.reset_group,), True, 200),
        ):
            client, user = self.operator(f"u{len(groups)}{is_staff}{expected}", groups, is_staff)
            for url in urls:
                self.assertEqual(client.get(url).status_code, expected, (user.username, url))
        root = Client()
        root.force_login(User.objects.create_superuser("raiz", "raiz@example.invalid", "x"))
        self.assertEqual(root.get(urls[0]).status_code, 200)
        staff, _ = self.operator("comum")
        self.assertNotContains(staff.get(reverse("staff_home")), reverse("pin_reset_search"))
        allowed, _ = self.operator("autorizado", (self.reset_group,))
        self.assertContains(allowed.get(reverse("staff_home")), reverse("pin_reset_search"))

    def test_search_by_full_phone_or_identifier_in_active_event_only(self):
        client, _ = self.operator(groups=(self.reset_group,))
        url = reverse("pin_reset_search")
        self.assertNotContains(client.get(url, {"q": "85999990000"}), self.p.name)  # GET não pesquisa
        for term in ("85999990000", "(85) 99999-0000", "+55 85 99999-0000", self.p.display_id, self.p.public_id.lower()):
            response = client.post(url, {"q": term})
            self.assertContains(response, self.p.name, msg_prefix=term)
            results = re.search(r'<ul class="pin-result-list">.*?</ul>', response.content.decode(), re.S).group()
            self.assertIn("(85) •••••-••00", results)
            self.assertNotIn("85999990000", results)
        for term in ("8599999", "Pessoa Sintética", "99990000"):
            response = client.post(url, {"q": term})
            self.assertNotContains(response, "pin-result-list", msg_prefix=term)
            self.assertNotContains(response, self.p.display_id, msg_prefix=term)
        other = Event.objects.create(name="Outro", slug="outro", active=False)
        stranger = make_passport(other, contact="85911112222", name="Pessoa Outro Evento")
        self.assertNotContains(client.post(url, {"q": "85911112222"}), "Pessoa Outro Evento")
        self.assertEqual(client.get(self.confirm_url(stranger)).status_code, 404)
        entry = AuditEntry.objects.filter(action="pin.search").first()
        self.assertNotIn("85999990000", str(entry.detail))

    def test_confirmation_page_shows_identity_data_masked(self):
        client, _ = self.operator(groups=(self.reset_group,))
        response = client.get(self.confirm_url())
        for text in (self.p.name, self.p.display_id, "(85) •••••-••00", "não comprovam identidade"):
            self.assertContains(response, text)
        self.assertNotContains(response, "85999990000")
        self.assertNotContains(response, "excecao_gestor")

    def test_reset_requires_csrf_and_in_person_check(self):
        csrf_client = Client(enforce_csrf_checks=True)
        user = User.objects.create_user("csrf", is_staff=True)
        user.groups.add(self.reset_group)
        csrf_client.force_login(user)
        self.assertEqual(csrf_client.post(self.confirm_url(), {"method": "aparelho", "confirmed": "on"}).status_code, 403)
        client, _ = self.operator(groups=(self.reset_group,))
        response = self.submit(client, {"confirmed": ""})
        self.assertContains(response, "Confirme que a conferência foi feita pessoalmente")
        response = self.submit(client, {"method": "excecao_gestor", "confirmed": "", "justification": "x" * 30})
        self.assertContains(response, "escolha válida")
        self.p.refresh_from_db()
        self.assertEqual(self.p.session_version, 1)

    def test_successful_reset_shows_pin_once_and_invalidates_sessions(self):
        visitor = Client()
        sign_in(visitor, self.p)
        client, operator = self.operator(groups=(self.reset_group,))
        with self.assertLogs("passport.security", level="INFO") as logs:
            response = self.submit(client)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        pin = re.search(r'class="pin-reveal-value"[^>]*>(\d{6})<', response.content.decode()).group(1)
        self.p.refresh_from_db()
        self.assertTrue(check_password(pin, self.p.pin_hash))
        self.assertFalse(check_password("123456", self.p.pin_hash))
        self.assertEqual(self.p.session_version, 2)
        self.assertNotIn(pin, "\n".join(logs.output))
        entry = AuditEntry.objects.get(action="visitor.pin_reset")
        self.assertEqual((entry.user, entry.target, entry.detail), (operator, self.p.public_id, {"metodo": "aparelho"}))
        self.assertNotIn(pin, str(entry.detail))
        self.assertNotIn(pin, str(dict(client.session)))
        # Sem banner persistente: a próxima página não mostra o PIN.
        self.assertNotContains(client.get(reverse("pin_reset_search")), pin)
        # Sessão anterior do visitante cai com explicação; o novo PIN funciona.
        response = visitor.get(reverse("passport"), follow=True)
        self.assertContains(response, "o PIN foi redefinido")
        self.assertRedirects(Client().post(reverse("recover"), {"contact": self.p.contact, "pin": pin}), reverse("passport"))

    def test_resubmission_and_quick_repeat_do_not_generate_new_pin(self):
        client, _ = self.operator(groups=(self.reset_group,))
        page = client.get(self.confirm_url())
        nonce = re.search(r'name="nonce" value="([^"]+)"', page.content.decode()).group(1)
        data = {"method": "aparelho", "confirmed": "on", "nonce": nonce}
        self.assertEqual(client.post(self.confirm_url(), data).status_code, 200)
        self.p.refresh_from_db()
        first_hash = self.p.pin_hash
        response = client.post(self.confirm_url(), data)
        self.assertContains(response, "Este envio já foi processado", status_code=409)
        response = self.submit(client)
        self.assertContains(response, "acabou de ser redefinido", status_code=409)
        self.p.refresh_from_db()
        self.assertEqual((self.p.pin_hash, self.p.session_version), (first_hash, 2))

    def test_resets_per_passport_are_limited(self):
        client, _ = self.operator(groups=(self.reset_group,))
        for expected_version in (2, 3, 4):
            self.assertEqual(self.submit(client).status_code, 200)
            AuditEntry.objects.update(created_at=timezone.now() - timedelta(minutes=5))
        response = self.submit(client)
        self.assertContains(response, "Limite de redefinições atingido")
        self.p.refresh_from_db()
        self.assertEqual(self.p.session_version, 4)

    def test_search_is_rate_limited(self):
        client, _ = self.operator(groups=(self.reset_group,))
        for _ in range(30):
            client.post(reverse("pin_reset_search"), {"q": "85999990000"})
        self.assertContains(client.post(reverse("pin_reset_search"), {"q": "85999990000"}), "Muitas consultas")

    def test_manager_exception_requires_both_permissions_and_justification(self):
        client, _ = self.operator(groups=(self.reset_group, self.manager_group))
        self.assertContains(client.get(self.confirm_url()), "excecao_gestor")
        response = self.submit(client, {"method": "excecao_gestor", "confirmed": "", "justification": "curta"})
        self.assertContains(response, "pelo menos 20 caracteres")
        reason = "Celular descarregado; identificador conferido com o passaporte impresso."
        response = self.submit(client, {"method": "excecao_gestor", "confirmed": "", "justification": reason})
        self.assertEqual(response.status_code, 200)
        entry = AuditEntry.objects.get(action="visitor.pin_reset")
        self.assertEqual(entry.detail, {"metodo": "excecao_gestor", "justificativa": reason})

    def test_admin_no_longer_offers_pin_reset_banner(self):
        root = Client()
        root.force_login(User.objects.create_superuser("raiz", "raiz@example.invalid", "x"))
        self.assertNotContains(root.get(reverse("admin:passport_passport_changelist")), "reset_visitor_pin")

    def test_visitor_guidance_explains_in_person_check(self):
        response = self.client.get(reverse("recover"))
        self.assertContains(response, "celular cadastrado em mãos")
        self.assertContains(response, "Saber o nome ou o número não basta")
