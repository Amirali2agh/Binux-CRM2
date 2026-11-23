from django.urls import path
from django.views.generic import RedirectView

from . import views
from .catalog import SECTIONS

app_name = "crm"
urlpatterns = [
    path("", RedirectView.as_view(pattern_name="crm:office_inventory", permanent=False), name="home"),
    path("internal/calendar/", views.calendar_view, name="calendar"),
    path("customers/", views.customer_list, name="customer_list"),
    path("customers/follow-ups/", views.customer_follow_ups, name="follow_ups"),
    path("customers/new/", views.customer_create, name="customer_create"),
    path("customers/tasks/", views.customer_tasks, name="tasks"),
    path("customers/completed/", views.completed_customers, name="completed_customers"),
    path("customers/archive/", views.customer_archive, name="customer_archive"),
    path("customers/trash/", views.customer_trash, name="customer_trash"),
    path("customers/<int:pk>/", views.customer_detail, name="customer_detail"),
    path(
        "customers/<int:pk>/calls/<int:call_pk>/outcome/",
        views.call_outcome_update,
        name="call_outcome_update",
    ),
    path("customers/<int:pk>/edit/", views.customer_update, name="customer_update"),
    path("customers/<int:pk>/delete/", views.customer_delete, name="customer_delete"),
    path("customers/<int:pk>/archive/", views.customer_archive_action, name="customer_archive_action"),
    path("customers/<int:pk>/restore/", views.customer_restore, name="customer_restore"),
]
for section in SECTIONS:
    for page in section["pages"]:
        if page["name"] in {
            "calendar", "customer_list", "follow_ups", "tasks", "completed_customers",
            "customer_archive", "customer_trash",
        }:
            continue
        urlpatterns.append(
            path(
                f"{section['slug']}/{page['slug']}/",
                views.display_page,
                {"page_key": page["name"]},
                name=page["name"],
            )
        )
