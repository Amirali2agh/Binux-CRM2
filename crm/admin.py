from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group

from .admin_site import crm_admin_site
from .models import Customer


@admin.register(Customer, site=crm_admin_site)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "business_name", "phone", "status", "assignee")
    list_filter = ("status", "source", "archived_at", "trashed_at")
    search_fields = ("name", "business_name", "phone")
    autocomplete_fields = ("assignee",)


crm_admin_site.register(get_user_model(), UserAdmin)
crm_admin_site.register(Group)
