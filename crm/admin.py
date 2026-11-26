from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group

from .admin_site import crm_admin_site
from .models import CallEvent, Customer


@admin.register(Customer, site=crm_admin_site)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "business_name", "phone", "status", "assignee")
    list_filter = ("status", "source", "archived_at", "trashed_at")
    search_fields = ("name", "business_name", "phone")
    autocomplete_fields = ("assignee",)


@admin.register(CallEvent, site=crm_admin_site)
class CallEventAdmin(admin.ModelAdmin):
    """Read-only visibility for webhook ingestion, including failures and unknown numbers."""

    list_display = (
        "received_at",
        "provider",
        "event_name",
        "disposition",
        "outcome",
        "normalized_phone",
    )
    list_filter = ("disposition", "provider", "event_name")
    search_fields = (
        "delivery_key",
        "external_event_id",
        "call_external_id",
        "normalized_phone",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]


crm_admin_site.register(get_user_model(), UserAdmin)
crm_admin_site.register(Group)
