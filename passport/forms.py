import re
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from .models import Stand


def normalize_phone(value):
    value = value.strip()
    if not re.fullmatch(r"\+?[0-9().\s-]+", value):
        raise ValidationError("Informe um celular válido com DDD.")
    digits = re.sub(r"[^0-9]", "", value)
    if len(digits) == 13 and digits.startswith("55"):
        digits = digits[2:]
    if not re.fullmatch(r"[1-9][0-9]9[0-9]{8}", digits):
        raise ValidationError("Informe o DDD e os nove dígitos do celular.")
    return digits


def normalize_contact(value):
    """Recupera contatos legados sem permitir novos cadastros por e-mail."""
    value = value.strip()
    if "@" in value:
        validate_email(value)
        return value.lower()
    try:
        return normalize_phone(value)
    except ValidationError:
        if not re.fullmatch(r"\+?[0-9().\s-]+", value):
            raise ValidationError("Informe o contato usado no cadastro.")
        digits = re.sub(r"[^0-9]", "", value)
        if not 10 <= len(digits) <= 15:
            raise ValidationError("Informe o contato usado no cadastro.")
        return digits


class RegistrationForm(forms.Form):
    name = forms.CharField(label="Nome", max_length=120, widget=forms.TextInput(attrs={"autocomplete": "name"}))
    contact = forms.CharField(label="Celular com DDD", max_length=22, widget=forms.TextInput(attrs={"type": "tel", "inputmode": "tel", "autocomplete": "tel-national", "placeholder": "(86) 99999-9999"}))
    pin = forms.RegexField(r"^[0-9]{6}$", label="Crie um PIN de 6 dígitos", widget=forms.PasswordInput(attrs={"inputmode": "numeric", "autocomplete": "new-password"}), error_messages={"invalid": "Use exatamente 6 números."})
    pin_confirm = forms.CharField(label="Confirme o PIN", widget=forms.PasswordInput(attrs={"inputmode": "numeric", "autocomplete": "new-password"}))
    marketing = forms.BooleanField(label="Quero receber no celular novidades do Senac sobre cursos e eventos.", required=False)

    def clean_contact(self):
        return normalize_phone(self.cleaned_data["contact"])

    def clean(self):
        data = super().clean()
        if data.get("pin") and data.get("pin_confirm") != data["pin"]:
            self.add_error("pin_confirm", "Os PINs não coincidem.")
        return data


class RecoveryForm(forms.Form):
    contact = forms.CharField(label="Celular cadastrado", max_length=254, widget=forms.TextInput(attrs={"type": "tel", "inputmode": "tel", "autocomplete": "tel-national", "placeholder": "(86) 99999-9999"}))
    pin = forms.RegexField(r"^[0-9]{6}$", label="PIN de 6 dígitos", widget=forms.PasswordInput(attrs={"inputmode": "numeric", "autocomplete": "current-password"}), error_messages={"invalid": "Use exatamente 6 números."})

    def clean_contact(self):
        return normalize_contact(self.cleaned_data["contact"])


class StandChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.name


class ManualStampForm(forms.Form):
    stand = StandChoiceField(label="Área ou estande", queryset=Stand.objects.none())
    code = forms.RegexField(r"^[0-9]{6}$", label="Código de 6 dígitos", widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code"}), error_messages={"invalid": "Informe os 6 números apresentados no estande."})

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["stand"].queryset = event.stands.filter(active=True)


class TicketLookupForm(forms.Form):
    code = forms.RegexField(r"^[0-9A-Fa-f]{10}$", label="Código de retirada", min_length=10, max_length=10, widget=forms.TextInput(attrs={"autocomplete": "off"}), error_messages={"invalid": "Informe o código de 10 caracteres."})

    def clean_code(self):
        return self.cleaned_data["code"].upper()
