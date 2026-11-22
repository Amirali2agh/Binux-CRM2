from django.contrib import admin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "business_name", "phone", "status", "assignee")
    list_filter = ("status", "source", "archived_at", "trashed_at")
    search_fields = ("name", "business_name", "phone")
    autocomplete_fields = ("assignee",)
