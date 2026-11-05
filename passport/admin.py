from django.contrib import admin
from .models import Event, Passport, Redemption, Stand, Stamp

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "active", "gap_seconds")

@admin.register(Stand)
class StandAdmin(admin.ModelAdmin):
    list_display = ("name", "event", "active", "required", "position")
    filter_horizontal = ("staff",)

@admin.register(Passport)
class PassportAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "event", "consent_marketing", "created_at")
    search_fields = ("name",)
    exclude = ("pin_hash", "contact_digest", "session_version")
    readonly_fields = ("contact", "name", "event", "consent_marketing", "consent_version", "consent_recorded_at", "last_stamp_at")
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
