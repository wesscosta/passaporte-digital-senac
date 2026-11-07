import re
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from .models import InterestSegment, Stand


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
    name = forms.CharField(label="Nome completo", max_length=120, widget=forms.TextInput(attrs={"autocomplete": "name"}))
    contact = forms.CharField(
        label="Celular/WhatsApp com DDD", max_length=22, help_text="Digite um número brasileiro com DDD. Exemplo: (86) 99999-9999.",
        widget=forms.TextInput(attrs={"type": "tel", "inputmode": "tel", "autocomplete": "tel-national", "placeholder": "(86) 99999-9999", "data-phone-mask": "br-mobile"}),
    )
    interest_segment = forms.ChoiceField(
        label="Qual segmento do Senac mais interessa a você?",
        choices=[("", "Selecione uma opção"), *InterestSegment.choices],
        error_messages={"required": "Selecione um segmento de interesse.", "invalid_choice": "Selecione um segmento válido."},
    )
    pin = forms.RegexField(r"^[0-9]{6}$", label="Crie um PIN de 6 dígitos", widget=forms.PasswordInput(attrs={"inputmode": "numeric", "autocomplete": "new-password"}), error_messages={"invalid": "Use exatamente 6 números."})
    pin_confirm = forms.CharField(label="Confirme o PIN", widget=forms.PasswordInput(attrs={"inputmode": "numeric", "autocomplete": "new-password"}))
    image_consent = forms.BooleanField(
        label="Autorizo o uso da minha imagem (foto e vídeo) em materiais de divulgação do Circuito Senac.",
        required=False,
    )
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
    remember = forms.BooleanField(label="Manter meu passaporte conectado neste dispositivo", required=False, initial=True)

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


class PassportSearchForm(forms.Form):
    q = forms.CharField(label="Nome, celular ou identificador", min_length=3, max_length=80, required=False,
                        widget=forms.TextInput(attrs={"type": "search", "autocomplete": "off", "enterkeyhint": "search"}),
                        error_messages={"min_length": "Digite pelo menos 3 caracteres."})


class IntervalForm(forms.Form):
    minutes = forms.IntegerField(label="Novo intervalo, em minutos", min_value=1, max_value=60,
                                 widget=forms.NumberInput(attrs={"inputmode": "numeric", "step": "1", "aria-describedby": "minutes-help"}),
                                 error_messages={"min_value": "Use pelo menos 1 minuto.", "max_value": "Use no máximo 60 minutos.",
                                                 "invalid": "Informe um número inteiro de minutos.", "required": "Informe o intervalo em minutos."})


class PinResetSearchForm(forms.Form):
    q = forms.CharField(
        label="Celular completo ou identificador do passaporte", min_length=8, max_length=30,
        widget=forms.TextInput(attrs={"autocomplete": "off", "autocapitalize": "characters", "spellcheck": "false",
                                      "enterkeyhint": "search"}),
        error_messages={"min_length": "Informe o celular completo com DDD ou o identificador completo.",
                        "required": "Informe o celular completo com DDD ou o identificador."},
    )


class PinResetForm(forms.Form):
    """Conferência presencial obrigatória; a exceção é restrita a gestores autorizados e exige justificativa."""
    METHOD_CHOICES = [
        ("aparelho", "O visitante mostrou, no próprio celular, o número cadastrado (configurações do telefone ou perfil do WhatsApp)."),
        ("ligacao", "Liguei ou enviei mensagem para o número cadastrado e a chamada ou mensagem chegou no celular que o visitante apresentou."),
    ]
    EXCEPTION = ("excecao_gestor", "Exceção de gestão: o visitante não consegue comprovar o acesso ao número agora.")
    method = forms.ChoiceField(label="Como você conferiu o acesso ao número cadastrado?", widget=forms.RadioSelect,
                               error_messages={"required": "Escolha como o acesso ao número foi conferido."})
    confirmed = forms.BooleanField(
        label="Confirmo que fiz essa conferência pessoalmente, agora, com o visitante presente.", required=False,
    )
    justification = forms.CharField(
        label="Justificativa da exceção", required=False, max_length=300,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Obrigatória só na exceção de gestão. Não inclua número de documento nem dados de saúde.",
    )

    def __init__(self, *args, allow_exception=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.allow_exception = allow_exception
        self.fields["method"].choices = self.METHOD_CHOICES + ([self.EXCEPTION] if allow_exception else [])
        if not allow_exception:
            del self.fields["justification"]

    def clean(self):
        data = super().clean()
        method = data.get("method")
        if method == "excecao_gestor":
            if len((data.get("justification") or "").strip()) < 20:
                self.add_error("justification", "Descreva a justificativa da exceção em pelo menos 20 caracteres.")
        elif method and not data.get("confirmed"):
            self.add_error("confirmed", "Confirme que a conferência foi feita pessoalmente com o visitante presente.")
        if method != "excecao_gestor":
            data["justification"] = ""
        return data
