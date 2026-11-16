from django.contrib import admin

from .models import LearningSubscriptionPlan


@admin.register(LearningSubscriptionPlan)
class LearningSubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = (
        "code", "name", "tier", "amount", "currency", "billing_interval", "is_active",
    )
    list_filter = ("tier", "is_active", "billing_interval")
    search_fields = ("code", "name", "description")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("tier", "code")

    def save_model(self, request, obj, form, change):
        # Model validation prevents an active premium plan without an explicitly
        # approved price/currency/interval. Provider setup alone cannot activate
        # checkout or premium entitlements.
        obj.full_clean()
        super().save_model(request, obj, form, change)
