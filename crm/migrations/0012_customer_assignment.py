import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0011_call_event_and_unknown_outcome"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomerAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("assigned_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("reclaimed_at", models.DateTimeField(blank=True, null=True)),
                ("assigned_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="customer_assignments_made", to=settings.AUTH_USER_MODEL)),
                ("assignee", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="customer_assignment_history", to=settings.AUTH_USER_MODEL)),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assignment_history", to="crm.customer")),
                ("reclaimed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="customer_assignments_reclaimed", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-assigned_at", "-pk")},
        ),
        migrations.AddConstraint(
            model_name="customerassignment",
            constraint=models.UniqueConstraint(condition=models.Q(reclaimed_at__isnull=True), fields=("customer",), name="one_active_assignment_per_customer"),
        ),
    ]
