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


from .models import Exam, ExamResult, Performance


class _AuditedAdmin(admin.ModelAdmin):
    actions = None  # no bulk delete: every delete goes through delete_model

    def _log(self, request, obj, action, extra=None):
        link = obj if isinstance(obj, Performance) and action != "admin_delete" else None
        MarkAuditLog.objects.create(
            performance=link, school_id=self._school_id(obj),
            user=request.user, action=action,
            details={"entity": obj._meta.model_name, "id": obj.pk, **(extra or {})},
        )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        self._log(request, obj, "admin_edit" if change else "admin_create",
                  {"changed": list(form.changed_data)})

    def delete_model(self, request, obj):
        self._log(request, obj, "admin_delete")
        super().delete_model(request, obj)


class _LockedAdmin(_AuditedAdmin):
    locked_when = ("locked",)

    def _is_locked(self, obj):
        return obj is not None and obj.status in self.locked_when

    def has_change_permission(self, request, obj=None):
        return not self._is_locked(obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return not self._is_locked(obj) and super().has_delete_permission(request, obj)


@admin.register(Performance)
class PerformanceAdmin(_LockedAdmin):
    def _school_id(self, obj):
        return obj.student.school_id


@admin.register(Exam)
class ExamAdmin(_LockedAdmin):
    locked_when = ("published",)

    def _school_id(self, obj):
        return obj.school_id


@admin.register(ExamResult)
class ExamResultAdmin(admin.ModelAdmin):
    actions = None  # computed snapshots: never add, change or delete here

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


from django.apps import apps
from django.contrib.admin.sites import AlreadyRegistered

for _m in apps.get_app_config("schools").get_models():
    try:
        admin.site.register(_m)
    except AlreadyRegistered:
        pass
