from django.shortcuts import render
from django.views.decorators.http import require_safe

from .catalog import PAGES, SECTIONS


@require_safe
def display_page(request, page_key):
    section, page = PAGES[page_key]
    return render(
        request,
        "crm/page.html",
        {
            "sections": SECTIONS,
            "page": page,
            "section": section,
            "current_page": page_key,
            "contract_reference": "DEMO-01",
            "display_rows": tuple(
                tuple(zip(page["columns"], row)) for row in page.get("rows", ())
            )
            if page["kind"] == "table"
            else (),
        },
    )
