from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import mock
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group, Permission, User
from django.db import IntegrityError, close_old_connections, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from passport.ids import ALPHABET, normalize_public_id
from passport.models import AuditEntry, Event, Passport, Redemption, Stamp, Stand
from passport.services import CONSENT_VERSION, digest, record_stamp, set_gap_minutes, station_code

FAST_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
AREAS = ["Tecnologia da Informação", "Artes e Design", "Gastronomia e Turismo", "Moda e Beleza", "Gestão e Comércio", "Saúde"]


def make_passport(event, contact="85999998888", name="Pessoa Teste"):
    return Passport.objects.create(
        event=event, name=name, contact=contact, contact_digest=digest("contact", contact),
        pin_hash=make_password("123456"), consent_version=CONSENT_VERSION, consent_recorded_at=timezone.now(),
    )


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class StaffBase(TestCase):
    def setUp(self):
        self.event = Event.objects.create(name="Teste", slug="teste", active=True)
        self.stands = [Stand.objects.create(event=self.event, name=n, position=i) for i, n in enumerate(AREAS)]
        self.prize_group = Group.objects.create(name="Premiação")

    def user(self, name, *, staff=True, stands=(), prize=False, manager=False, superuser=False):
        if superuser:
            u = User.objects.create_superuser(name, password="secret")
        else:
            u = User.objects.create_user(name, password="secret", is_staff=staff)
        for s in stands:
            s.staff.add(u)
        if prize:
            u.groups.add(self.prize_group)
        if manager:
            gestao, _ = Group.objects.get_or_create(name="Gestão")
            gestao.permissions.add(Permission.objects.get(codename="manage_event"))
            u.groups.add(gestao)
        return u

    def client_for(self, user):
        c = Client()
        c.force_login(user)
        return c


class PermissionTests(StaffBase):
    def routes(self, p):
        return {
            "search": reverse("passport_search"),
            "detail": reverse("passport_detail", args=[p.display_id]),
            "manager": reverse("manager_home"),
            "prize": reverse("prize_lookup"),
            "station": reverse("station", args=[self.stands[1].pk]),
        }

    def statuses(self, client, p):
        return {k: client.get(url).status_code for k, url in self.routes(p).items()}

    def test_anonymous_is_sent_to_login_on_every_staff_route(self):
        p = make_passport(self.event)
        for url in self.routes(p).values():
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertIn(reverse("staff_login"), response["Location"])

    def test_non_staff_account_is_refused(self):
        p = make_passport(self.event)
        statuses = self.statuses(self.client_for(self.user("visitante", staff=False)), p)
        self.assertEqual(set(statuses.values()), {403})

    def test_staff_without_assignment_cannot_search_or_manage(self):
        p = make_passport(self.event)
        statuses = self.statuses(self.client_for(self.user("solto")), p)
        self.assertEqual(set(statuses.values()), {403})

    def test_station_staff_searches_but_does_not_manage_or_redeem(self):
        p = make_passport(self.event)
        statuses = self.statuses(self.client_for(self.user("estande", stands=[self.stands[0]])), p)
        self.assertEqual(statuses, {"search": 200, "detail": 200, "manager": 403, "prize": 403, "station": 403})

    def test_prize_staff_keeps_prize_access_without_management(self):
        p = make_passport(self.event)
        statuses = self.statuses(self.client_for(self.user("premio", prize=True)), p)
        self.assertEqual(statuses, {"search": 200, "detail": 200, "manager": 403, "prize": 200, "station": 403})

    def test_manager_permission_without_superuser_does_not_grant_prize(self):
        p = make_passport(self.event)
        statuses = self.statuses(self.client_for(self.user("gestor", manager=True)), p)
        self.assertEqual(statuses, {"search": 200, "detail": 200, "manager": 200, "prize": 403, "station": 200})

    def test_superuser_is_manager_and_keeps_prize_access(self):
        p = make_passport(self.event)
        statuses = self.statuses(self.client_for(self.user("root", superuser=True)), p)
        self.assertEqual(set(statuses.values()), {200})

    def test_manager_permission_requires_staff_flag(self):
        u = self.user("gestor", manager=True)
        u.is_staff = False
        u.save()
        self.assertEqual(self.client_for(u).get(reverse("manager_home")).status_code, 403)

    def test_direct_post_by_non_manager_does_not_change_interval(self):
        c = self.client_for(self.user("estande", stands=[self.stands[0]]))
        self.assertEqual(c.post(reverse("manager_home"), {"minutes": 1}).status_code, 403)
        self.event.refresh_from_db()
        self.assertEqual(self.event.gap_seconds, 300)
        self.assertFalse(AuditEntry.objects.exists())

    def test_staff_home_shows_only_permitted_tools(self):
        html = self.client_for(self.user("estande", stands=[self.stands[0]])).get(reverse("staff_home")).content.decode()
        self.assertIn(reverse("passport_search"), html)
        self.assertNotIn(reverse("manager_home"), html)
        self.assertNotIn(reverse("prize_lookup"), html)
        html = self.client_for(self.user("gestor", manager=True)).get(reverse("staff_home")).content.decode()
        self.assertIn(reverse("manager_home"), html)

    def test_detail_cannot_register_delivery(self):
        p = make_passport(self.event)
        c = self.client_for(self.user("root", superuser=True))
        self.assertEqual(c.post(reverse("passport_detail", args=[p.display_id])).status_code, 405)
        self.assertEqual(c.post(reverse("passport_search")).status_code, 405)
        self.assertFalse(Redemption.objects.exists())


class SearchTests(StaffBase):
    def setUp(self):
        super().setUp()
        self.c = self.client_for(self.user("estande", stands=[self.stands[0]]))

    def search(self, q, **extra):
        return self.c.get(reverse("passport_search"), {"q": q, **extra})

    def test_search_by_name_fragment_masks_contact(self):
        p = make_passport(self.event, "85999998888", "Maria Fictícia")
        response = self.search("fictí")
        self.assertContains(response, "Maria Fictícia")
        self.assertContains(response, "(85) •••••-••88")
        self.assertContains(response, p.display_id)
        html = response.content.decode()
        for secret in ("85999998888", "99999-8888", p.pin_hash, p.contact_digest):
            self.assertNotIn(secret, html)

    def test_search_by_phone_accepts_registration_formats(self):
        make_passport(self.event, "85999998888", "Maria Fictícia")
        for q in ("(85) 99999-8888", "85 99999 8888", "+55 85 99999-8888", "5585999998888"):
            self.assertContains(self.search(q), "Maria Fictícia", msg_prefix=q)

    def test_search_by_phone_finds_legacy_country_code_record(self):
        make_passport(self.event, "5585988887777", "Registro Legado")
        response = self.search("(85) 98888-7777")
        self.assertContains(response, "Registro Legado")
        self.assertContains(response, "(85) •••••-••77")

    def test_partial_phone_does_not_list_visitors(self):
        make_passport(self.event, "85999998888", "Maria Fictícia")
        self.assertNotContains(self.search("8888"), "Maria Fictícia")

    def test_search_by_identifier_ignores_case_and_hyphen(self):
        p = make_passport(self.event, name="Ana Teste")
        self.assertContains(self.search(p.display_id.lower()), "Ana Teste")
        self.assertContains(self.search(p.public_id), "Ana Teste")

    def test_short_or_empty_term_runs_no_search(self):
        make_passport(self.event)
        self.assertContains(self.search("ab"), "pelo menos 3 caracteres")
        self.assertNotContains(self.c.get(reverse("passport_search")), "Pessoa Teste")
        self.assertFalse(AuditEntry.objects.exists())

    def test_results_are_paginated(self):
        for i in range(25):
            make_passport(self.event, f"8599999{i:04d}", f"Visitante {i:02d}")
        first = self.search("Visitante")
        self.assertEqual(first.content.decode().count('data-label="Nome"'), 20)
        self.assertContains(first, "25 passaportes encontrados, página 1 de 2")
        second = self.search("Visitante", pagina=2)
        self.assertEqual(second.content.decode().count('data-label="Nome"'), 5)

    def test_other_event_is_not_searchable(self):
        other = Event.objects.create(name="Outro", slug="outro", active=False)
        p = make_passport(other, name="Outro Evento")
        response = self.search("Outro Evento")
        self.assertContains(response, "Nenhum passaporte encontrado")
        self.assertNotContains(response, p.display_id)
        self.assertEqual(self.c.get(reverse("passport_detail", args=[p.display_id])).status_code, 404)

    def test_progress_and_prize_status(self):
        p = make_passport(self.event, name="Ana Teste")
        self.assertContains(self.search("Ana Teste"), "Ainda não elegível")
        now = timezone.now()
        for s in self.stands:
            Stamp.objects.create(passport=p, stand=s, created_at=now)
        response = self.search("Ana Teste")
        self.assertContains(response, "6 de 6")
        self.assertContains(response, "Elegível")
        Redemption.objects.create(passport=p, staff=User.objects.create_user("x", is_staff=True))
        self.assertContains(self.search("Ana Teste"), "Entrega registrada")

    def test_search_and_view_are_audited_without_the_term(self):
        p = make_passport(self.event, "85999998888", "Maria Fictícia")
        self.search("(85) 99999-8888")
        self.c.get(reverse("passport_detail", args=[p.display_id]))
        search, view = AuditEntry.objects.order_by("pk")
        self.assertEqual(search.action, "passport.search")
        self.assertEqual(search.detail, {"tipo": "celular", "pagina": 1, "resultados": 1})
        self.assertEqual(view.action, "passport.view")
        self.assertEqual(view.target, p.public_id)
        self.assertNotIn("9999", str(search.detail) + view.target)

    def test_detail_shows_badges_and_masked_contact(self):
        p = make_passport(self.event, "85999998888", "Maria Fictícia")
        Stamp.objects.create(passport=p, stand=self.stands[0], created_at=timezone.now())
        response = self.c.get(reverse("passport_detail", args=[p.display_id]))
        self.assertContains(response, "(85) •••••-••88")
        self.assertNotContains(response, "85999998888")
        self.assertContains(response, "is-earned", count=1)
        self.assertContains(response, "is-pending", count=5)


class IntervalTests(StaffBase):
    def setUp(self):
        super().setUp()
        self.manager = self.user("root", superuser=True)
        self.c = self.client_for(self.manager)

    def test_manager_sees_current_value_in_minutes(self):
        response = self.c.get(reverse("manager_home"))
        self.assertContains(response, "5 minutos")
        self.assertContains(response, 'value="5"')

    def test_change_is_saved_in_event_and_audited(self):
        with self.assertLogs("passport.security", "INFO") as logs:
            response = self.c.post(reverse("manager_home"), {"minutes": 10}, follow=True)
        self.assertContains(response, "Intervalo alterado de 5 minutos para 10 minutos")
        self.event.refresh_from_db()
        self.assertEqual(self.event.gap_seconds, 600)
        entry = AuditEntry.objects.get()
        self.assertEqual((entry.user, entry.action, entry.detail), (self.manager, "event.gap", {"de_segundos": 300, "para_segundos": 600}))
        self.assertIsNotNone(entry.created_at)
        self.assertIn(f"por_id={self.manager.pk}", logs.output[0])

    def test_invalid_values_are_rejected(self):
        for value in ("0", "61", "abc", "", "2.5", "-3"):
            response = self.c.post(reverse("manager_home"), {"minutes": value})
            self.assertEqual(response.status_code, 200, value)
        self.event.refresh_from_db()
        self.assertEqual(self.event.gap_seconds, 300)
        self.assertFalse(AuditEntry.objects.exists())

    def test_post_requires_csrf(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.manager)
        self.assertEqual(c.post(reverse("manager_home"), {"minutes": 10}).status_code, 403)
        self.event.refresh_from_db()
        self.assertEqual(self.event.gap_seconds, 300)

    def test_existing_non_minute_value_is_preserved_until_saved(self):
        Event.objects.filter(pk=self.event.pk).update(gap_seconds=90)
        response = self.c.get(reverse("manager_home"))
        self.assertContains(response, "1 minuto e 30 s")
        self.assertContains(response, "não é um número inteiro de minutos")
        self.event.refresh_from_db()
        self.assertEqual(self.event.gap_seconds, 90)

    def test_change_applies_to_next_stamp_and_keeps_existing_stamps(self):
        p = make_passport(self.event)
        t0 = timezone.now()
        a, b = self.stands[0], self.stands[1]
        self.assertEqual(record_stamp(p.pk, 1, a.pk, station_code(a, t0), t0)[0], "ok")
        later = t0 + timedelta(minutes=6)
        set_gap_minutes(self.event.pk, 10, self.manager)
        result, seconds = record_stamp(p.pk, 1, b.pk, station_code(b, later), later)
        self.assertEqual((result, seconds), ("wait", 240))
        set_gap_minutes(self.event.pk, 5, self.manager)
        self.assertEqual(record_stamp(p.pk, 1, b.pk, station_code(b, later), later)[0], "ok")
        self.assertEqual(Stamp.objects.filter(passport=p).count(), 2)

    def test_reducing_interval_does_not_remove_stamps(self):
        p = make_passport(self.event)
        Stamp.objects.create(passport=p, stand=self.stands[0], created_at=timezone.now())
        self.c.post(reverse("manager_home"), {"minutes": 1})
        self.assertEqual(Stamp.objects.count(), 1)

    def test_participant_texts_follow_new_interval(self):
        self.c.post(reverse("manager_home"), {"minutes": 7})
        self.assertContains(self.client.get(reverse("home")), "7 minutos")
        p = make_passport(self.event)
        visitor = Client()
        session = visitor.session
        session["passport_id"], session["passport_version"] = p.pk, p.session_version
        session.save()
        self.assertContains(visitor.get(reverse("passport")), "Aguarde 7 minutos entre carimbos registrados")

    def test_manager_lists_stands_without_identified_area(self):
        Stand.objects.create(event=self.event, name="Estande Extra", position=9)
        response = self.c.get(reverse("manager_home"))
        self.assertContains(response, "7 estandes ativos")
        self.assertContains(response, "Sem área identificada pelo nome")
        self.assertContains(response, "Estande Extra")


class PublicIdTests(StaffBase):
    def test_new_passports_get_unique_readable_ids(self):
        ids = {make_passport(self.event, f"8599999{i:04d}").public_id for i in range(50)}
        self.assertEqual(len(ids), 50)
        for value in ids:
            self.assertEqual(len(value), 8)
            self.assertTrue(set(value) <= set(ALPHABET))
            self.assertEqual(normalize_public_id(f"{value[:4]}-{value[4:]}".lower()), value)

    def test_id_is_stable_after_save(self):
        p = make_passport(self.event)
        original = p.public_id
        p.name = "Outro Nome"
        p.save()
        p.refresh_from_db()
        self.assertEqual(p.public_id, original)

    def test_collision_is_retried(self):
        first = make_passport(self.event, "85999990001")
        with mock.patch("passport.models.new_public_id", side_effect=[first.public_id, "ZZZZ2222"]):
            second = make_passport(self.event, "85999990002")
        self.assertEqual(second.public_id, "ZZZZ2222")

    def test_database_rejects_duplicate_id(self):
        first = make_passport(self.event, "85999990001")
        second = make_passport(self.event, "85999990002")
        with self.assertRaises(IntegrityError):
            Passport.objects.filter(pk=second.pk).update(public_id=first.public_id)

    def test_passport_page_shows_identifier(self):
        p = make_passport(self.event)
        session = self.client.session
        session["passport_id"], session["passport_version"] = p.pk, p.session_version
        session.save()
        self.assertContains(self.client.get(reverse("passport")), f"Passaporte nº <strong>{p.display_id}</strong>")


class BadgeTests(StaffBase):
    def setUp(self):
        super().setUp()
        self.p = make_passport(self.event)
        session = self.client.session
        session["passport_id"], session["passport_version"] = self.p.pk, self.p.session_version
        session.save()

    def page(self):
        return self.client.get(reverse("passport")).content.decode()

    def test_all_badges_start_pending(self):
        html = self.page()
        self.assertEqual(html.count("is-pending"), 6)
        self.assertEqual(html.count("A conquistar"), 6)
        self.assertNotIn("is-earned", html)

    def test_badge_is_earned_only_after_server_confirms_stamp(self):
        a = self.stands[0]
        url = reverse("scan_stamp", args=[a.pk, station_code(a)])
        self.client.get(url)
        self.assertNotIn("is-earned", self.page())
        self.client.post(url)
        html = self.page()
        self.assertEqual(html.count("is-earned"), 1)
        self.assertIn("badge-tech is-earned", html)
        self.assertIn("Conquistada às", html)

    def test_invalid_code_does_not_earn_badge(self):
        a = self.stands[0]
        self.client.post(reverse("scan_stamp", args=[a.pk, "000000" if station_code(a) != "000000" else "111111"]))
        self.assertNotIn("is-earned", self.page())

    def test_each_area_has_its_badge_style(self):
        html = self.page()
        for key in ("tech", "arts", "food", "fashion", "commerce", "health"):
            self.assertIn(f"badge-{key} is-pending", html)

    def test_configurable_stands_and_unknown_area(self):
        Stand.objects.create(event=self.event, name="Estande Extra", position=9)
        self.stands[5].active = False
        self.stands[5].save()
        Stand.objects.create(event=self.event, name="GESCOM Anexo", position=10)
        html = self.page()
        self.assertEqual(html.count('class="badge '), 7)
        self.assertEqual(html.count("badge-default"), 2)
        self.assertNotIn("badge-health", html)

    def test_area_names_tolerate_accents_case_and_acronym(self):
        from passport.areas import area_key
        for name, key in (("SAUDE", "health"), ("GESCOM", "commerce"), (" tecnologia  da informacao ", "tech")):
            self.assertEqual(area_key(Stand(name=name)), key)

    def test_badge_state_is_not_color_only(self):
        self.client.post(reverse("scan_stamp", args=[self.stands[0].pk, station_code(self.stands[0])]))
        html = self.page()
        self.assertIn("seal-check", html)
        self.assertIn("seal-outline", html)


class PublicIdMigrationTests(TransactionTestCase):
    def test_existing_passports_receive_unique_ids_without_other_changes(self):
        executor = MigrationExecutor(connection)
        executor.migrate([("passport", "0001_initial")])
        apps = executor.loader.project_state([("passport", "0001_initial")]).apps
        OldEvent, OldPassport = apps.get_model("passport", "Event"), apps.get_model("passport", "Passport")
        event = OldEvent.objects.create(name="Antigo", slug="antigo", active=True, gap_seconds=90)
        before = []
        for i in range(30):
            old = OldPassport.objects.create(
                event=event, name=f"Legado {i}", contact=f"55859999{i:05d}", contact_digest=f"d{i}",
                pin_hash="x", consent_version="v1", consent_recorded_at=timezone.now(),
            )
            before.append((old.pk, old.name, old.contact, old.contact_digest, old.session_version))
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        rows = list(Passport.objects.order_by("pk"))
        self.assertEqual([(r.pk, r.name, r.contact, r.contact_digest, r.session_version) for r in rows], before)
        self.assertEqual(len({r.public_id for r in rows}), 30)
        self.assertTrue(all(normalize_public_id(r.public_id) for r in rows))
        self.assertEqual(Event.objects.get(slug="antigo").gap_seconds, 90)


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class ConcurrencyTests(TransactionTestCase):
    def run_together(self, *calls):
        barrier = Barrier(len(calls))

        def run(fn):
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                return fn()
            except Exception as exc:  # noqa: BLE001 - o teste compara o tipo do erro
                return exc
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(calls)) as pool:
            return list(pool.map(run, calls))

    def test_same_public_id_twice_only_one_insert_succeeds(self):
        event = Event.objects.create(name="Teste", slug="teste", active=True)
        with mock.patch("passport.models.Passport.objects.filter") as filt:
            filt.return_value.exists.return_value = False
            with mock.patch("passport.models.new_public_id", return_value="ABCD2345"):
                results = self.run_together(
                    lambda: make_passport(event, "85999990001"), lambda: make_passport(event, "85999990002"),
                )
        self.assertEqual(sum(isinstance(r, Passport) for r in results), 1)
        self.assertEqual(sum(isinstance(r, IntegrityError) for r in results), 1)
        self.assertEqual(Passport.objects.filter(public_id="ABCD2345").count(), 1)

    def test_interval_change_and_stamp_at_same_time_stay_consistent(self):
        event = Event.objects.create(name="Teste", slug="teste", active=True, gap_seconds=300)
        a = Stand.objects.create(event=event, name="A")
        b = Stand.objects.create(event=event, name="B")
        manager = User.objects.create_superuser("root", password="secret")
        p = make_passport(event)
        t0 = timezone.now() - timedelta(minutes=6)
        Stamp.objects.create(passport=p, stand=a, created_at=t0)
        Passport.objects.filter(pk=p.pk).update(last_stamp_at=t0)
        now = timezone.now()
        stamp_result, _ = self.run_together(
            lambda: record_stamp(p.pk, 1, b.pk, station_code(b, now), now)[0],
            lambda: set_gap_minutes(event.pk, 10, manager),
        )
        # Com 5 min o carimbo passa; com 10 min, espera. Qualquer ordem é válida, mas nunca carimbo parcial.
        self.assertIn(stamp_result, ("ok", "wait"))
        self.assertEqual(Stamp.objects.filter(passport=p).count(), 2 if stamp_result == "ok" else 1)
        event.refresh_from_db()
        self.assertEqual(event.gap_seconds, 600)
        self.assertEqual(AuditEntry.objects.count(), 1)
