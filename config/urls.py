from django.contrib.auth import views as auth_views
from django.urls import include, path

from crm import admin as crm_admin  # noqa: F401 - registers CRM models on the role-aware site
from crm.admin_site import crm_admin_site
from crm.views import TeamLoginView

urlpatterns = [
    path("admin/", crm_admin_site.urls),
    path("accounts/login/", TeamLoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("crm.urls")),
]
