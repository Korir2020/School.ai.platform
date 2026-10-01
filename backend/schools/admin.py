from django.contrib import admin
from .models import School

admin.site.register(School)

from django.contrib import admin
from .models import MarkAuditLog


@admin.register(MarkAuditLog)
class MarkAuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "school", "user", "action", "performance")
    list_filter = ("school", "action")
    readonly_fields = [f.name for f in MarkAuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
