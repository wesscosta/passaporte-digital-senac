from django.conf import settings
from django.db import models
from .areas import area_key
from .ids import format_public_id, new_public_id


class Event(models.Model):
    name = models.CharField("nome", max_length=160)
    slug = models.SlugField(unique=True)
    active = models.BooleanField("ativo", default=False)
    gap_seconds = models.PositiveIntegerField("intervalo em segundos", default=300)

    class Meta:
        # Permissão do gestor: o superusuário a recebe implicitamente; um grupo restrito pode recebê-la sem ser superusuário.
        permissions = [
            ("manage_event", "Pode gerenciar o evento ativo e o intervalo entre carimbos"),
            # Concedida explicitamente (grupo ou usuário); não decorre de is_staff nem da gestão.
            ("reset_pin", "Pode redefinir o PIN de visitantes após conferência presencial"),
        ]

    def __str__(self):
        return self.name


class Stand(models.Model):
    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="stands")
    name = models.CharField("nome", max_length=160)
    position = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    required = models.BooleanField("exigido para premiação", default=True)
    staff = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="assigned_stands")

    class Meta:
        ordering = ["position", "name"]
        constraints = [models.UniqueConstraint(fields=["event", "name"], name="unique_stand_in_event")]

    @property
    def area_key(self):
        return area_key(self)

    def __str__(self):
        return f"{self.name} — {self.event.name}"


class InterestSegment(models.TextChoices):
    MODA = "moda", "Moda"
    BELEZA = "beleza", "Beleza"
    SAUDE = "saude", "Saúde"
    TECNOLOGIA = "tecnologia", "Tecnologia da Informação"
    GASTRONOMIA = "gastronomia", "Gastronomia"
    ARTES = "artes_design", "Artes e Design"
    COMUNICACAO = "comunicacao", "Comunicação"
    GESTAO = "gestao_comercio", "Gestão e Comércio"
    TURISMO = "turismo", "Turismo"
    OUTRAS = "outras", "Outras"


class Passport(models.Model):
    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="passports")
    # Identificador de atendimento, não é senha nem prova de identidade.
    public_id = models.CharField("identificador", max_length=8, unique=True, editable=False)
    name = models.CharField(max_length=120)
    contact = models.CharField(max_length=254)
    contact_digest = models.CharField(max_length=64)
    pin_hash = models.CharField(max_length=256)
    session_version = models.PositiveIntegerField(default=1)
    interest_segment = models.CharField(
        "segmento de interesse", max_length=24, choices=InterestSegment.choices, blank=True, default="",
    )
    consent_marketing = models.BooleanField(default=False)
    consent_version = models.CharField(max_length=80)
    consent_recorded_at = models.DateTimeField()
    # None identifica registros anteriores à introdução da escolha de imagem.
    consent_image = models.BooleanField("autorização de imagem", null=True, blank=True, default=None)
    consent_image_version = models.CharField("versão da autorização de imagem", max_length=80, blank=True, default="")
    consent_image_recorded_at = models.DateTimeField("registro da escolha de imagem", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_stamp_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["event", "contact_digest"], name="unique_contact_in_event")]

    def save(self, *args, **kwargs):
        if not self.public_id:
            # A restrição única no banco é a garantia final; a consulta só evita a colisão comum.
            candidate = new_public_id()
            while Passport.objects.filter(public_id=candidate).exists():
                candidate = new_public_id()
            self.public_id = candidate
        super().save(*args, **kwargs)

    @property
    def display_id(self):
        return format_public_id(self.public_id)

    def __str__(self):
        return f"Passaporte {self.display_id or self.pk} — {self.name}"


class Stamp(models.Model):
    passport = models.ForeignKey(Passport, on_delete=models.PROTECT, related_name="stamps")
    stand = models.ForeignKey(Stand, on_delete=models.PROTECT, related_name="stamps")
    created_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["passport", "stand"], name="unique_stamp_per_stand")]


class ScanVoucher(models.Model):
    """Comprovante de leitura válida do QR de um estande, emitido antes do cadastro ou da entrada.

    O valor bruto fica só na sessão do navegador; o banco guarda o digest. Vale por poucos minutos e é
    consumido uma única vez, na mesma transação do carimbo.
    """
    token_digest = models.CharField(max_length=64, unique=True)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="+")
    stand = models.ForeignKey(Stand, on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField()
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    consumed_by = models.ForeignKey("Passport", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    # Primeiro passaporte que tentou usar o comprovante (por exemplo, em espera). Outro visitante que entre depois
    # no mesmo navegador não pode aproveitar a leitura.
    claimed_by = models.ForeignKey("Passport", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")


class RateBucket(models.Model):
    key = models.CharField(max_length=64, unique=True)
    window_start = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)


class RedemptionTicket(models.Model):
    passport = models.OneToOneField(Passport, on_delete=models.CASCADE, related_name="ticket")
    code_digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()


class Redemption(models.Model):
    passport = models.OneToOneField(Passport, on_delete=models.PROTECT, related_name="redemption")
    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class AuditEntry(models.Model):
    """Ações da equipe. Guarda quem, quando, o quê e o id do alvo; nunca o termo pesquisado, telefone ou PIN."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    action = models.CharField(max_length=40)
    target = models.CharField(max_length=40, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "registro de auditoria"
        verbose_name_plural = "registros de auditoria"
