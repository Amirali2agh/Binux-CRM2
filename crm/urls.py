from django.urls import path

from . import views
from .catalog import SECTIONS

app_name = "crm"
urlpatterns = [
    path("", views.home, name="home"),
    path("management/dashboard/", views.manager_call_dashboard, name="manager_dashboard"),
    path("internal/calendar/", views.calendar_view, name="calendar"),
    path("internal/settings/users/", views.user_management, name="user_management"),
    path("customers/", views.customer_list, name="customer_list"),
    path("customers/follow-ups/", views.customer_follow_ups, name="follow_ups"),
    path("customers/new/", views.customer_create, name="customer_create"),
    path("customers/assign/", views.customer_assignment, name="customer_assignment"),
    path(
        "customers/assignments/<int:assignment_pk>/reclaim/",
        views.customer_assignment_reclaim,
        name="customer_assignment_reclaim",
    ),
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
    path(
        "integrations/noghtefone/webhook/",
        views.noghtefone_webhook,
        name="noghtefone_webhook",
    ),
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
