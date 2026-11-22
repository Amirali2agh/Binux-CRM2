from django.urls import path
from django.views.generic import RedirectView

from .catalog import SECTIONS
from .views import display_page

app_name = "crm"
urlpatterns = [
    path(
        "",
        RedirectView.as_view(pattern_name="crm:office_inventory", permanent=False),
        name="home",
    )
]
for section in SECTIONS:
    for page in section["pages"]:
        urlpatterns.append(
            path(
                f"{section['slug']}/{page['slug']}/",
                display_page,
                {"page_key": page["name"]},
                name=page["name"],
            )
        )
