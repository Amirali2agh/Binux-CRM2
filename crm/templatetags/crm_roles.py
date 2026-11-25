from django import template

from crm.roles import MANAGER_GROUP, is_manager, is_marketer


register = template.Library()


@register.filter
def has_crm_role(user, role_name):
    if role_name == MANAGER_GROUP:
        return is_manager(user)
    from crm.roles import MARKETER_GROUP

    return role_name == MARKETER_GROUP and is_marketer(user)


@register.filter
def for_user(sections, user):
    if is_manager(user):
        return sections
    if not is_marketer(user):
        return ()
    visible_pages = {"customer_list", "follow_ups"}
    return tuple(
        {**section, "pages": tuple(
            page for page in section["pages"] if page["name"] in visible_pages
        )}
        for section in sections
        if section["slug"] == "customers"
    )
