from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from .services import blocked_until, client_address, limit, limit_reset

# Janela fixa de 15 minutos. O limite por conta barra a adivinhação de senha de um funcionário;
# o limite por endereço é mais alto para não travar a equipe que compartilha a rede do evento.
WINDOW_SECONDS = 900
MAX_PER_ACCOUNT = 5
MAX_PER_ADDRESS = 50


def account_key(username):
    return username.strip().casefold()


def account_blocked_until(username):
    return blocked_until("staff_login.account", account_key(username), MAX_PER_ACCOUNT, WINDOW_SECONDS)


def unlock_account(username):
    return limit_reset("staff_login.account", account_key(username))


class ThrottledLoginMixin:
    """Consome a tentativa antes de verificar a senha; o acerto libera a conta."""

    def clean(self):
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if username is not None and password:
            account = account_key(username)
            address = client_address(self.request) if self.request else "unknown"
            if not limit("staff_login.ip", address, MAX_PER_ADDRESS, WINDOW_SECONDS) or not limit(
                "staff_login.account", account, MAX_PER_ACCOUNT, WINDOW_SECONDS
            ):
                # A mesma mensagem para contas existentes ou não; a senha nem é verificada.
                raise ValidationError(
                    "Muitas tentativas de acesso. Aguarde 15 minutos e tente novamente.", code="rate_limited"
                )
            data = super().clean()
            limit_reset("staff_login.account", account)
            return data
        return super().clean()


class StaffAuthenticationForm(ThrottledLoginMixin, AuthenticationForm):
    pass


class StaffAdminAuthenticationForm(ThrottledLoginMixin, AdminAuthenticationForm):
    pass
