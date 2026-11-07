"""Correções da auditoria de UX de 06/11/2026 (A1, A2, A5, M1–M7, D0). Dados sintéticos."""
import re
from datetime import timedelta
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group, Permission, User
from django.test import RequestFactory, TestCase, override_settings
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone
from passport.models import Event, Passport, Redemption, RedemptionTicket, Stamp, Stand
from passport.services import CONSENT_VERSION, digest, issue_ticket, record_stamp, redeem, station_code
from passport.version import VersionHeaderMiddleware
from passport.views import next_stamp_at

FAST_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class VisitorRecoveryTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(name="Teste", slug="teste", active=True)
        self.a = Stand.objects.create(event=self.event, name="Área A", position=1)
        self.b = Stand.objects.create(event=self.event, name="Área B", position=2)
        self.p = Passport.objects.create(
            event=self.event, name="Pessoa Sintética", contact="85999990000",
            contact_digest=digest("contact", "85999990000"), pin_hash=make_password("123456"),
            consent_version=CONSENT_VERSION, consent_recorded_at=timezone.now(),
        )
        session = self.client.session
        session["passport_id"], session["passport_version"] = self.p.pk, self.p.session_version
        session.save()

    # A1
    def test_no_required_stand_does_not_ask_to_complete_required_stands(self):
        Stand.objects.update(required=False)
        response = self.client.get(reverse("passport"))
        self.assertContains(response, "ainda não foi liberada pela organização")
        self.assertNotContains(response, "Complete os estandes obrigatórios")
        Stand.objects.filter(pk=self.a.pk).update(required=True)
        self.assertContains(self.client.get(reverse("passport")), "Complete os estandes obrigatórios")

    # A2
    def test_paused_event_keeps_visitor_signed_in(self):
        Event.objects.filter(pk=self.event.pk).update(active=False)
        response = self.client.get(reverse("passport"))
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "O evento está pausado", status_code=503)
        self.assertEqual(self.client.session["passport_id"], self.p.pk)
        Event.objects.filter(pk=self.event.pk).update(active=True)
        self.assertEqual(self.client.get(reverse("passport")).status_code, 200)

    def test_other_active_event_ends_old_passport_session(self):
        Event.objects.filter(pk=self.event.pk).update(active=False)
        Event.objects.create(name="Novo", slug="novo", active=True)
        self.assertRedirects(self.client.get(reverse("passport")), reverse("recover"))
        self.assertNotIn("passport_id", self.client.session)

    def test_paused_event_blocks_stamps_and_redemption_and_keeps_session(self):
        Stand.objects.filter(pk=self.b.pk).update(required=False)
        # Concluído antes da pausa: apto à retirada.
        Stamp.objects.create(passport=self.p, stand=self.a, created_at=timezone.now() - timedelta(hours=1))
        code_b = station_code(self.b)
        Event.objects.filter(pk=self.event.pk).update(active=False)
        scan = reverse("scan_stamp", args=[self.b.pk, code_b])
        for method, url, data in (
            ("get", scan, None), ("post", scan, None),
            ("post", reverse("manual_stamp"), {"stand": self.b.pk, "code": code_b}),
            ("post", reverse("issue_redemption"), None),
        ):
            response = getattr(self.client, method)(url, data)
            self.assertEqual(response.status_code, 503, (method, url))
            self.assertContains(response, "O evento está pausado", status_code=503)
        self.assertEqual(Stamp.objects.count(), 1)
        self.assertFalse(RedemptionTicket.objects.exists())
        self.assertEqual(self.client.session["passport_id"], self.p.pk)
        self.assertNotIn("pending_scan", self.client.session)
        # Defesa no serviço: mesmo sem passar pela view, nada é registrado durante a pausa.
        self.assertEqual(record_stamp(self.p.pk, self.p.session_version, self.b.pk, code_b)[0], "invalid")
        self.assertIsNone(issue_ticket(self.p.pk, self.p.session_version))
        Event.objects.filter(pk=self.event.pk).update(active=True)
        self.assertRedirects(self.client.post(reverse("issue_redemption")), reverse("passport") + "#codigo-retirada",
                             fetch_redirect_response=False)

    def test_redemption_is_not_confirmed_during_pause(self):
        Stand.objects.filter(pk=self.b.pk).update(required=False)
        Stamp.objects.create(passport=self.p, stand=self.a, created_at=timezone.now())
        code = issue_ticket(self.p.pk, self.p.session_version)
        Event.objects.filter(pk=self.event.pk).update(active=False)
        self.assertEqual(redeem(code, User.objects.create_user("premio", is_staff=True)), "invalid")
        self.assertFalse(Redemption.objects.exists())

    # M1: a interface nunca mostra um horário anterior à liberação do servidor, e no horário mostrado o servidor aceita.
    def test_displayed_time_matches_server_rule(self):
        for gap, offset in ((300, 0), (300, 20), (90, 59), (60, 0)):
            Event.objects.filter(pk=self.event.pk).update(gap_seconds=gap)
            Stamp.objects.all().delete()
            last = timezone.now().replace(microsecond=0) - timedelta(seconds=5) + timedelta(seconds=offset)
            Stamp.objects.create(passport=self.p, stand=self.a, created_at=last)
            Passport.objects.filter(pk=self.p.pk).update(last_stamp_at=last)
            self.p.refresh_from_db()
            self.p.event.refresh_from_db()
            ready = last + timedelta(seconds=gap)
            shown = next_stamp_at(self.p, now=last)
            self.assertGreaterEqual(shown, ready)
            self.assertLess(shown - ready, timedelta(minutes=1))
            code_at = lambda moment: station_code(self.b, moment)
            before = ready - timedelta(seconds=1)
            self.assertEqual(record_stamp(self.p.pk, 1, self.b.pk, code_at(before), before)[0], "wait")
            self.assertEqual(record_stamp(self.p.pk, 1, self.b.pk, code_at(shown), shown)[0], "ok")
            Stamp.objects.filter(stand=self.b).delete()

    # A5
    def test_replaced_session_explains_why_visitor_must_sign_in(self):
        Passport.objects.filter(pk=self.p.pk).update(session_version=2)  # outro aparelho ou PIN redefinido
        response = self.client.get(reverse("passport"), follow=True)
        self.assertEqual(response.redirect_chain[-1][0], reverse("recover"))
        self.assertContains(response, "foi aberto em outro aparelho ou o PIN foi redefinido")
        self.assertNotContains(self.client.get(reverse("recover")), "outro aparelho ou o PIN")

    # M1
    def test_wait_message_uses_same_time_as_passport(self):
        now = timezone.now()
        Stamp.objects.create(passport=self.p, stand=self.a, created_at=now - timedelta(seconds=10))
        Passport.objects.filter(pk=self.p.pk).update(last_stamp_at=now - timedelta(seconds=10))
        response = self.client.post(reverse("manual_stamp"), {"stand": self.b.pk, "code": station_code(self.b)}, follow=True)
        self.p.refresh_from_db()
        shown = timezone.localtime(next_stamp_at(self.p)).strftime("%H:%M")
        html = response.content.decode()
        message = re.search(r'<div class="messages".*?</div>\s*</div>', html, re.S).group()
        self.assertIn(f"Seu próximo carimbo fica disponível às {shown}.", message)
        self.assertNotRegex(message, r"\d\d:\d\d:\d\d")
        # O passaporte, logo abaixo, mostra o mesmo horário.
        self.assertIn(f">{shown}</time>", html)

    def test_wait_message_follows_interval_changed_by_manager(self):
        now = timezone.now()
        Stamp.objects.create(passport=self.p, stand=self.a, created_at=now - timedelta(seconds=10))
        Passport.objects.filter(pk=self.p.pk).update(last_stamp_at=now - timedelta(seconds=10))
        Event.objects.filter(pk=self.event.pk).update(gap_seconds=1200)
        response = self.client.post(reverse("manual_stamp"), {"stand": self.b.pk, "code": station_code(self.b)}, follow=True)
        expected = timezone.localtime(now - timedelta(seconds=10) + timedelta(seconds=1200))
        if expected.second or expected.microsecond:
            expected = expected.replace(second=0, microsecond=0) + timedelta(minutes=1)
        self.assertContains(response, f"disponível às {expected:%H:%M}.")

    # M3
    def test_wrong_manual_code_keeps_visitor_on_form_with_stand(self):
        wrong = f"{(int(station_code(self.b)) + 1) % 1_000_000:06d}"
        response = self.client.post(reverse("manual_stamp"), {"stand": self.b.pk, "code": wrong})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confira o estande escolhido")
        self.assertEqual(response.context["form"]["stand"].value(), str(self.b.pk))
        self.assertEqual(response.context["form"]["code"].value(), wrong)
        self.assertNotContains(response, 'class="message error"')
        self.assertFalse(Stamp.objects.exists())
        ok = self.client.post(reverse("manual_stamp"), {"stand": self.b.pk, "code": station_code(self.b)})
        self.assertRedirects(ok, reverse("passport"), fetch_redirect_response=False)
        self.assertTrue(Stamp.objects.filter(stand=self.b).exists())

    # M4
    def test_back_to_confirmation_of_stamped_stand_shows_existing_stamp(self):
        url = reverse("scan_stamp", args=[self.a.pk, station_code(self.a)])
        self.client.post(url)
        response = self.client.get(url)
        stamp = Stamp.objects.get()
        self.assertContains(response, "Você já carimbou este estande às")
        self.assertContains(response, timezone.localtime(stamp.created_at).strftime("%H:%M"))
        self.assertNotContains(response, "Confirmar carimbo")
        # Mesmo com o código já expirado, não pede para ler o QR de novo.
        old = reverse("scan_stamp", args=[self.a.pk, station_code(self.a, timezone.now() - timedelta(seconds=180))])
        self.assertNotContains(self.client.get(old), "Ler o QR novamente")

    # M7
    def test_redemption_code_shows_validity_and_is_anchored(self):
        Stand.objects.filter(pk=self.b.pk).update(required=False)
        Event.objects.filter(pk=self.event.pk).update(gap_seconds=0)
        self.client.post(reverse("scan_stamp", args=[self.a.pk, station_code(self.a)]))
        response = self.client.post(reverse("issue_redemption"))
        self.assertRedirects(response, reverse("passport") + "#codigo-retirada", fetch_redirect_response=False)
        page = self.client.get(reverse("passport"))
        expires = timezone.localtime(RedemptionTicket.objects.get().expires_at).strftime("%H:%M")
        self.assertContains(page, 'id="codigo-retirada"')
        self.assertContains(page, f">{expires}</time>. Depois disso, gere um novo código.")


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class RegistrationErrorSummaryTests(TestCase):
    def setUp(self):
        Event.objects.create(name="Teste", slug="teste", active=True)

    # M2
    def test_errors_are_summarized_focused_and_data_is_kept(self):
        response = self.client.post(reverse("register"), {
            "name": "Pessoa Sintética", "contact": "86 9999", "pin": "1234", "pin_confirm": "1234", "marketing": "on",
        })
        html = response.content.decode()
        summary = re.search(r'<div class="error-summary"[^>]*>.*?</div>', html, re.S)
        self.assertIsNotNone(summary)
        self.assertIn("autofocus", summary.group())
        self.assertIn('tabindex="-1"', summary.group())
        for field in ("id_contact", "id_interest_segment", "id_pin"):
            self.assertIn(f'href="#{field}"', summary.group())
        self.assertIn("Digite o PIN e a confirmação novamente", summary.group())
        self.assertLess(html.index("error-summary"), html.index('<form method="post"'))
        self.assertIn('value="Pessoa Sintética"', html)
        self.assertNotIn('value="1234"', html)

    def test_duplicate_contact_error_appears_once_in_summary(self):
        data = {"name": "Pessoa", "contact": "85999998888", "pin": "123456", "pin_confirm": "123456", "interest_segment": "saude"}
        self.client.post(reverse("register"), data)
        self.client.cookies.clear()
        response = self.client.post(reverse("register"), data)
        self.assertContains(response, "Não foi possível cadastrar", count=1)
        self.assertContains(response, "error-summary")

    def test_valid_form_has_no_summary(self):
        self.assertNotContains(self.client.get(reverse("register")), "error-summary")


class StaffGuidanceTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(name="Teste", slug="teste", active=True)
        self.a = Stand.objects.create(event=self.event, name="Área A", position=1)

    def login(self, user):
        self.client.force_login(user)
        return self.client

    # M5
    def test_forbidden_pages_explain_and_offer_navigation(self):
        staff = User.objects.create_user("estande", is_staff=True)
        c = self.login(staff)
        for url, message in (
            (reverse("station", args=[self.a.pk]), "Este estande não está atribuído à sua conta."),
            (reverse("manager_home"), "Acesso restrito à gestão do evento."),
            (reverse("prize_lookup"), "Acesso restrito à equipe de premiação."),
        ):
            response = c.get(url)
            self.assertEqual(response.status_code, 403)
            self.assertContains(response, message, status_code=403)
            self.assertContains(response, "Voltar ao painel da equipe", status_code=403)
            self.assertContains(response, "<h1>Acesso não permitido</h1>", status_code=403, html=False)

    def test_forbidden_for_non_team_account_has_no_staff_panel_link(self):
        c = self.login(User.objects.create_user("comum"))
        response = c.get(reverse("staff_home"))
        self.assertEqual(response.status_code, 403)
        self.assertNotContains(response, "Voltar ao painel da equipe", status_code=403)
        self.assertContains(response, "Sair e entrar com outra conta", status_code=403)

    # A1 e M6
    def manager(self):
        group = Group.objects.create(name="Gestão")
        group.permissions.add(Permission.objects.get(codename="manage_event"))
        user = User.objects.create_user("gestor", is_staff=True)
        user.groups.add(group)
        return self.login(user)

    def test_manager_is_warned_when_prize_cannot_be_claimed(self):
        c = self.manager()
        self.assertNotContains(c.get(reverse("manager_home")), "Nenhum estande ativo é obrigatório")
        Stand.objects.update(required=False)
        response = c.get(reverse("manager_home"))
        self.assertContains(response, "Nenhum estande ativo é obrigatório")
        self.assertContains(response, "0 obrigatórios para a premiação")
        Stand.objects.update(active=False)
        self.assertContains(c.get(reverse("manager_home")), "Nenhum estande ativo: visitantes não conseguem")

    def test_manager_without_admin_rights_is_not_sent_to_admin(self):
        c = self.manager()
        response = c.get(reverse("manager_home"))
        self.assertContains(response, "configurados pelo administrador do sistema")
        self.assertNotContains(response, "/admin/")
        Event.objects.create(name="Outro", slug="outro", active=True)
        response = c.get(reverse("manager_home"))
        self.assertContains(response, "Peça ao administrador do sistema")
        self.assertNotContains(response, "Ajuste os eventos no administrativo")
        self.assertNotContains(response, "/admin/")

    def test_admin_shortcut_follows_effective_permission_not_staff_flag(self):
        group = Group.objects.create(name="Gestão")
        group.permissions.add(Permission.objects.get(codename="manage_event"))
        stands_url = reverse("admin:passport_stand_changelist")
        events_url = reverse("admin:passport_event_changelist")
        manager = User.objects.create_user("gestor", is_staff=True)
        manager.groups.add(group)
        self.assertNotContains(self.login(manager).get(reverse("manager_home")), stands_url)
        # Permissão concedida por grupo (efetiva via has_perm) libera somente o atalho correspondente.
        editors = Group.objects.create(name="Edição de estandes")
        editors.permissions.add(Permission.objects.get(codename="change_stand"))
        manager.groups.add(editors)
        manager = User.objects.get(pk=manager.pk)  # descarta o cache de permissões
        response = self.login(manager).get(reverse("manager_home"))
        self.assertContains(response, stands_url)
        Event.objects.create(name="Outro", slug="outro", active=True)
        self.assertNotContains(self.client.get(reverse("manager_home")), events_url)
        # Superusuário inativo não tem permissões efetivas nem chega à tela.
        inactive = User.objects.create_superuser("inativo", "inativo@example.invalid", "x")
        inactive.is_active = False
        inactive.save()
        self.client.logout()
        self.client.force_login(inactive)
        self.assertNotEqual(self.client.get(reverse("manager_home")).status_code, 200)

    def test_superuser_gets_admin_shortcuts(self):
        c = self.login(User.objects.create_superuser("raiz", "raiz@example.invalid", "x"))
        self.assertContains(c.get(reverse("manager_home")), reverse("admin:passport_stand_changelist"))

    # M7
    def test_prize_review_shows_passport_identifier(self):
        p = Passport.objects.create(
            event=self.event, name="Pessoa Sintética", contact="85999990001",
            contact_digest=digest("contact", "85999990001"), pin_hash="x",
            consent_version=CONSENT_VERSION, consent_recorded_at=timezone.now(),
        )
        Stamp.objects.create(passport=p, stand=self.a, created_at=timezone.now())
        RedemptionTicket.objects.create(passport=p, code_digest=digest("ticket", "ABCDEF1234"),
                                        expires_at=timezone.now() + timedelta(minutes=5))
        prize = Group.objects.create(name="Premiação")
        user = User.objects.create_user("premio", is_staff=True)
        user.groups.add(prize)
        response = self.login(user).get(reverse("prize_review", args=["ABCDEF1234"]))
        self.assertContains(response, p.display_id)


class VersionTests(TestCase):
    # D0
    def run_middleware(self, commit):
        with self.settings(APP_COMMIT=commit):
            middleware = VersionHeaderMiddleware(lambda request: HttpResponse("ok"))
        return middleware(RequestFactory().get("/"))

    def test_version_header_only_for_valid_commit(self):
        self.assertEqual(self.run_middleware("c3f97e0")["X-App-Version"], "c3f97e0")
        self.assertNotIn("X-App-Version", self.run_middleware(""))
        self.assertNotIn("X-App-Version", self.run_middleware("v1; <script>"))

    def test_templates_no_longer_use_manual_cache_busting(self):
        Event.objects.create(name="Teste", slug="teste", active=True)
        self.assertNotContains(self.client.get(reverse("home")), "?v=")
