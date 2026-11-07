import re

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from passport.models import Event, Passport


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CsrfRecoveryTests(TestCase):
    def setUp(self):
        Event.objects.create(name="Evento de teste", slug="teste", active=True)

    def test_missing_token_is_rejected_with_safe_retry_page(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse("register"), {"name": "Nome fictício"})
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "este envio não foi processado", status_code=403)
        self.assertContains(response, f'href="{reverse("register")}"', status_code=403)
        self.assertNotContains(response, "Nome fictício", status_code=403)
        self.assertNotContains(response, "CSRF token", status_code=403)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertFalse(Passport.objects.exists())

    def test_login_rotates_token_and_reopening_form_recovers(self):
        User.objects.create_user("staff_teste", password="senha-ficticia", is_staff=True)
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("register"))
        old_token = client.cookies["csrftoken"].value
        login = client.post(reverse("staff_login"), {
            "username": "staff_teste", "password": "senha-ficticia",
            "csrfmiddlewaretoken": old_token,
        })
        self.assertEqual(login.status_code, 302)
        self.assertNotEqual(old_token, client.cookies["csrftoken"].value)
        fields = {
            "name": "Visitante Fictício", "contact": "10900000002",
            "pin": "741852", "pin_confirm": "741852", "interest_segment": "tecnologia",
        }
        rejected = client.post(reverse("register"), {**fields, "csrfmiddlewaretoken": old_token})
        self.assertEqual(rejected.status_code, 403)
        self.assertContains(rejected, "Reabrir página", status_code=403)
        self.assertFalse(Passport.objects.exists())

        client.get(reverse("register"))
        fresh_token = client.cookies["csrftoken"].value
        accepted = client.post(reverse("register"), {**fields, "csrfmiddlewaretoken": fresh_token})
        self.assertEqual(accepted.status_code, 302)
        self.assertEqual(Passport.objects.count(), 1)

    def test_post_only_action_returns_to_passport(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse("issue_redemption"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, f'href="{reverse("passport")}"', status_code=403)

    def test_external_referer_is_never_used_as_retry_url(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse("register"), HTTP_REFERER="https://example.org/malicioso")
        html = response.content.decode()
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("example.org", html)
        self.assertIsNotNone(re.search(r'href="/cadastro/"', html))
