from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.utils import timezone
from .auth import StaffAdminAuthenticationForm, account_blocked_until, unlock_account
from .models import AuditEntry, Event, Passport, RateBucket, Redemption, Stand, Stamp
from .services import security_log

# O /admin/ usa o mesmo limite de tentativas do acesso da equipe.
admin.site.login_form = StaffAdminAuthenticationForm

User = get_user_model()
admin.site.unregister(User)


@admin.register(User)
class StaffUserAdmin(UserAdmin):
    list_display = (*UserAdmin.list_display, "login_blocked_until")
    actions = ["unlock_staff_login"]

    @admin.display(description="Acesso bloqueado até")
    def login_blocked_until(self, obj):
        until = account_blocked_until(obj.get_username())
        return f"{timezone.localtime(until):%H:%M}" if until else "—"

    @admin.action(description="Desbloquear acesso da equipe", permissions=["change"])
    def unlock_staff_login(self, request, queryset):
        unlocked = 0
        for user in queryset:
            if unlock_account(user.get_username()):
                unlocked += 1
                self.log_change(request, user, "Desbloqueio manual do limite de tentativas de acesso.")
                security_log.info("Acesso desbloqueado manualmente: usuario_id=%s por_id=%s", user.pk, request.user.pk)
        if unlocked:
            self.message_user(request, f"Contas com tentativas zeradas: {unlocked}.", messages.SUCCESS)
        else:
            self.message_user(request, "Nenhuma conta selecionada tinha tentativas registradas.", messages.INFO)


@admin.register(RateBucket)
class RateBucketAdmin(admin.ModelAdmin):
    """Contadores de tentativas. Excluir um registro libera o bloqueio correspondente (por exemplo, de um endereço).
    A chave é derivada; procure pela chave registrada no log de segurança."""
    list_display = ("key", "window_start", "count")
    search_fields = ("key",)
    ordering = ("-window_start",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def delete_model(self, request, obj):
        security_log.info("Contador de tentativas removido manualmente: chave=%s por_id=%s", obj.key, request.user.pk)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for key in queryset.values_list("key", flat=True):
            security_log.info("Contador de tentativas removido manualmente: chave=%s por_id=%s", key, request.user.pk)
        super().delete_queryset(request, queryset)

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "active", "gap_seconds")

@admin.register(Stand)
class StandAdmin(admin.ModelAdmin):
    list_display = ("name", "event", "active", "required", "position")
    filter_horizontal = ("staff",)

@admin.register(Passport)
class PassportAdmin(admin.ModelAdmin):
    list_display = ("id", "public_id", "name", "event", "consent_marketing", "created_at")
    search_fields = ("name", "public_id")
    exclude = ("pin_hash", "contact_digest", "session_version")
    readonly_fields = ("public_id", "contact", "name", "event", "consent_marketing", "consent_version", "consent_recorded_at", "last_stamp_at")
    def has_add_permission(self, request):
        return False

@admin.register(Stamp)
class StampAdmin(admin.ModelAdmin):
    list_display = ("passport", "stand", "created_at")
    readonly_fields = ("passport", "stand", "created_at")
    def has_add_permission(self, request):
        return False

@admin.register(Redemption)
class RedemptionAdmin(admin.ModelAdmin):
    list_display = ("passport", "staff", "created_at")
    readonly_fields = ("passport", "staff", "created_at")
    def has_add_permission(self, request):
        return False


@admin.register(AuditEntry)
class AuditEntryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "target")
    list_filter = ("action",)
    readonly_fields = ("created_at", "user", "action", "target", "detail")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
