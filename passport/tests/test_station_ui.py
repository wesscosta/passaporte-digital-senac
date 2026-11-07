import re
from datetime import timedelta
from unittest import mock

import qrcode
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from passport.models import Event, Stand
from passport.services import station_code


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StationDisplayTests(TestCase):
    def setUp(self):
        event = Event.objects.create(name="Evento de teste", slug="teste", active=True)
        self.stand = Stand.objects.create(event=event, name="Artes e Design")
        user = User.objects.create_user("staff_teste", password="senha-ficticia", is_staff=True)
        self.stand.staff.add(user)
        self.client.force_login(user)

    def test_qr_appears_before_manual_code_with_clear_update_interval(self):
        response = self.client.get(reverse("station", args=[self.stand.pk]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('<body class="station-mode">', html)
        self.assertIn('class="station-logo"', html)
        self.assertIn("Escaneie o QR code", html)
        self.assertIn("a cada minuto", html)
        self.assertIn("data-station-progress", html)
        self.assertIn("data-station-seconds", html)
        self.assertNotIn("Voltar aos estandes", html)
        self.assertLess(html.index('class="station-qr"'), html.index('class="station-code"'))
        self.assertIn('alt="QR code para registrar visita em Artes e Design"', html)
        self.assertNotIn("ESCANEIE COM O CELULAR</div>", html)

    def test_qr_and_manual_code_share_the_same_time_window(self):
        start = timezone.now()
        for instant in (start, start + timedelta(minutes=1)):
            with self.subTest(instant=instant), \
                 mock.patch("passport.views.timezone.now", return_value=instant), \
                 mock.patch("passport.views.qrcode.make", wraps=qrcode.make) as generate:
                response = self.client.get(reverse("station", args=[self.stand.pk]))
                expected = station_code(self.stand, instant)
                html = response.content.decode()
                self.assertIn(f'class="station-code">{expected}</strong>', html)
                self.assertTrue(generate.call_args.args[0].endswith(
                    reverse("scan_stamp", args=[self.stand.pk, expected])
                ))
                milliseconds = int(re.search(r'data-refresh-ms="(\d+)"', html).group(1))
                self.assertGreaterEqual(milliseconds, 1)
                self.assertLessEqual(milliseconds, 60000)
                self.assertAlmostEqual(milliseconds, (60 - instant.timestamp() % 60) * 1000, delta=1)

    def test_staff_stand_link_opens_a_new_tab_with_notice(self):
        response = self.client.get(reverse("staff_home"))
        self.assertContains(response, 'target="_blank" rel="noopener"')
        self.assertContains(response, "abre em nova aba")
