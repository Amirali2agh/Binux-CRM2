from functools import wraps

from django.contrib.admin import AdminSite
from django.core.exceptions import PermissionDenied

from .roles import MANAGER_GROUP, MARKETER_GROUP


class CRMAdminSite(AdminSite):
    site_header = "Binux CRM"
    site_title = "Binux CRM"
    index_title = "مدیریت سامانه"

    def admin_view(self, view, cacheable=False):
        admin_response = super().admin_view(view, cacheable=cacheable)

        @wraps(view)
        def marketer_forbidden(request, *args, **kwargs):
            if request.user.is_authenticated and request.user.groups.filter(
                name=MARKETER_GROUP
            ).exists():
                raise PermissionDenied
            return admin_response(request, *args, **kwargs)

        return marketer_forbidden

    def has_permission(self, request):
        user = request.user
        if not user.is_authenticated or not user.is_active:
            return False
        if user.groups.filter(name=MARKETER_GROUP).exists():
            return False
        if user.groups.filter(name=MANAGER_GROUP).exists():
            return user.is_staff
        # Preserve a controlled bootstrap route: an unassigned superuser can
        # explicitly assign the first CRM role in Django admin. No role is
        # inferred or granted by migration.
        return user.is_superuser and not user.groups.filter(
            name__in=(MANAGER_GROUP, MARKETER_GROUP)
        ).exists()


crm_admin_site = CRMAdminSite(name="admin")
