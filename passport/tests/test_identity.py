"""Identidade visual do hero e das insígnias: artes oficiais (cópias web), decorativas e sem dados reais."""
import re
from django.contrib.auth.hashers import make_password
from django.contrib.staticfiles import finders
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from passport.models import Event, Passport, Stand
from passport.services import CONSENT_VERSION, digest, station_code

FAST_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
AREAS = {
    "Tecnologia da Informação": "tecnologia", "Artes e Design": "artes", "Gastronomia e Turismo": "gastronomia",
    "Moda e Beleza": "moda", "Gestão e Comércio": "gestao", "Saúde": "saude",
}


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class IdentityTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(name="Teste", slug="teste", active=True)
        self.stands = [Stand.objects.create(event=self.event, name=n, position=i) for i, n in enumerate(AREAS)]

    def login_passport(self):
        contact = "85999990000"
        p = Passport.objects.create(
            event=self.event, name="Pessoa Teste", contact=contact, contact_digest=digest("contact", contact),
            pin_hash=make_password("123456"), consent_version=CONSENT_VERSION, consent_recorded_at=timezone.now(),
        )
        session = self.client.session
        session["passport_id"], session["passport_version"] = p.pk, p.session_version
        session.save()
        return p

    def passport_html(self):
        return self.client.get(reverse("passport")).content.decode()

    def test_identity_copies_are_served_as_static_files(self):
        names = ["logo-circuito.svg", "logo-circuito-compacto.svg", "grafismo.png", "grafismo-lateral.svg", "grafismo-esquerdo.svg", "grafismo-direito.svg"] + [f"{a}.{ext}" for a in AREAS.values() for ext in ("svg", "webp")]
        for name in names:
            self.assertIsNotNone(finders.find(f"passport/identity/{name}"), name)

    def test_hero_uses_official_logo_and_graphic_as_decoration(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn("marca-circuito.webp", html)
        art = re.search(r'<div class="hero-art" aria-hidden="true">(.*?)</div>', html, re.S)
        self.assertIsNotNone(art)
        self.assertIn("passport/identity/logo-circuito.svg", art.group(1))
        self.assertIn("passport/identity/grafismo.png", art.group(1))
        self.assertEqual(art.group(1).count('alt=""'), art.group(1).count("<img"))
        self.assertIn("<h1>", html)

    def test_branding_is_shared_without_repeated_demo_banner(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('passport/identity/logo-circuito-compacto.svg', html)
        self.assertIn('class="footer-brand"', html)
        self.assertNotIn('demo-banner', html)
        self.assertNotIn('versão de desenvolvimento', html)
        registration = self.client.get(reverse("register")).content.decode()
        self.assertIn('Ambiente de teste: não informe dados reais.', registration)

    def test_registration_uses_dedicated_wide_submit(self):
        html = self.client.get(reverse("register")).content.decode()
        self.assertIn('class="button form-submit form-submit--registration"', html)

    def test_footer_links_use_existing_destinations(self):
        html = self.client.get(reverse("home")).content.decode()
        footer = re.search(r'<footer class="footer">(.*?)</footer>', html, re.S)
        self.assertIsNotNone(footer)
        self.assertIn('aria-label="Navegação do rodapé"', footer.group(1))
        self.assertIn(f'href="{reverse("home")}#como-funciona"', footer.group(1))
        self.assertIn(f'href="{reverse("staff_home")}"', footer.group(1))

    def test_visit_card_is_one_link_with_both_methods_on_next_screen(self):
        self.login_passport()
        html = self.passport_html()
        card = re.search(r'<a class="action-panel".*?</a>', html, re.S)
        self.assertIsNotNone(card)
        self.assertIn(f'href="{reverse("manual_stamp")}"', card.group())
        self.assertIn("QR code ou digite o código", card.group())
        self.assertEqual(card.group().count("<a "), 1)
        self.assertNotIn("<button", card.group())
        next_page = self.client.get(reverse("manual_stamp")).content.decode()
        self.assertIn('id="leitor"', next_page)
        self.assertIn('id="codigo"', next_page)

    def test_visit_card_describes_wait_when_next_stamp_is_pending(self):
        p = self.login_passport()
        Passport.objects.filter(pk=p.pk).update(last_stamp_at=timezone.now())
        html = self.passport_html()
        card = re.search(r'<a class="action-panel".*?</a>', html, re.S)
        self.assertIsNotNone(card)
        self.assertIn('aria-describedby="visit-help next-stamp-message"', card.group())
        self.assertIn('id="next-stamp-message"', card.group())

    def test_each_area_badge_uses_its_official_art_with_svg_fallback(self):
        self.login_passport()
        html = self.passport_html()
        for art in AREAS.values():
            self.assertIn(f'srcset="/static/passport/identity/{art}.webp" type="image/webp"', html)
            self.assertIn(f'src="/static/passport/identity/{art}.svg"', html)
        self.assertEqual(html.count('class="badge-figure" aria-hidden="true"'), 6)
        self.assertEqual(html.count('<picture class="badge-art">'), 6)
        self.assertNotIn("badge-seal", html)

    def test_badge_images_are_decorative_and_state_stays_textual(self):
        self.login_passport()
        a = self.stands[0]
        self.client.post(reverse("scan_stamp", args=[a.pk, station_code(a)]))
        html = self.passport_html()
        pictures = re.findall(r'<picture class="badge-art">(.*?)</picture>', html, re.S)
        imgs = [tag for picture in pictures for tag in re.findall(r'<img [^>]*>', picture)]
        self.assertEqual(len(imgs), 6)
        self.assertTrue(all('alt=""' in tag for tag in imgs))
        self.assertEqual(html.count("Conquistada às"), 1)
        self.assertEqual(html.count("A conquistar"), 5)
        self.assertIn("badge-tech is-earned", html)
        self.assertIn("seal-check", html)
        self.assertIn("seal-outline", html)

    def test_unknown_area_keeps_neutral_seal_without_official_art(self):
        Stand.objects.create(event=self.event, name="Estande Extra", position=9)
        self.login_passport()
        html = self.passport_html()
        self.assertEqual(html.count('class="badge '), 7)
        self.assertEqual(html.count("badge-default"), 1)
        self.assertEqual(html.count('<svg class="badge-seal"'), 1)
        self.assertEqual(html.count('<picture class="badge-art">'), 6)
