from functools import wraps

from django.core.exceptions import PermissionDenied


MANAGER_GROUP = "CRM Manager"
MARKETER_GROUP = "CRM Marketer"


def has_role(user, group_name):
    if not user.is_authenticated or not user.is_active:
        return False
    assigned_roles = set(
        user.groups.filter(name__in=(MANAGER_GROUP, MARKETER_GROUP)).values_list(
            "name", flat=True
        )
    )
    return assigned_roles == {group_name}


def is_manager(user):
    return has_role(user, MANAGER_GROUP)


def is_marketer(user):
    return has_role(user, MARKETER_GROUP)


def role_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not (is_manager(request.user) or is_marketer(request.user)):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapped


def manager_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not is_manager(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapped


def customer_queryset_for_user(queryset, user):
    if is_marketer(user) and not is_manager(user):
        return queryset.filter(assignee=user)
    return queryset
