from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from crm.views import TeamLoginView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", TeamLoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("crm.urls")),
]
