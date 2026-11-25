from django.conf import settings
from django.db import migrations


MANAGER_GROUP = "CRM Manager"
MARKETER_GROUP = "CRM Marketer"


def create_role_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    database = schema_editor.connection.alias
    for group_name in (MANAGER_GROUP, MARKETER_GROUP):
        Group.objects.using(database).get_or_create(name=group_name)


def keep_role_groups(apps, schema_editor):
    # Role groups may have members; rollback must not revoke assigned roles.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0008_customernumbersequence_customer_customer_number_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(create_role_groups, keep_role_groups),
    ]
