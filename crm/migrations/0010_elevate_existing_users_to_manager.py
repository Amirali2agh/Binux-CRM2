from django.conf import settings
from django.db import migrations


MANAGER_GROUP = "CRM Manager"
MARKETER_GROUP = "CRM Marketer"


def promote_existing_users(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    Group = apps.get_model("auth", "Group")
    database = schema_editor.connection.alias
    manager, _ = Group.objects.using(database).get_or_create(name=MANAGER_GROUP)
    marketer, _ = Group.objects.using(database).get_or_create(name=MARKETER_GROUP)

    groups_field = User._meta.get_field("groups")
    through = groups_field.remote_field.through
    user_field = groups_field.m2m_field_name()
    group_field = groups_field.m2m_reverse_field_name()
    user_column = f"{user_field}_id"
    group_column = f"{group_field}_id"

    user_ids = User.objects.using(database).values_list("pk", flat=True)
    through.objects.using(database).bulk_create(
        [
            through(**{user_column: user_id, group_column: manager.pk})
            for user_id in user_ids.iterator()
        ],
        ignore_conflicts=True,
        batch_size=500,
    )
    through.objects.using(database).filter(**{group_column: marketer.pk}).delete()


def keep_manager_access(apps, schema_editor):
    # Rolling back must not unexpectedly revoke the explicitly granted access.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0009_crm_role_groups"),
        ("crm", "0009_category_customer_numbers"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(promote_existing_users, keep_manager_access),
    ]
