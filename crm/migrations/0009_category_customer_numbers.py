from django.db import migrations, models


PREFIXES = {
    "company": "C",
    "micro_business": "A",
    "crm": "M",
    "erp": "E",
}


def categorize_existing_numbers(apps, schema_editor):
    Customer = apps.get_model("crm", "Customer")
    Sequence = apps.get_model("crm", "CustomerNumberSequence")
    database = schema_editor.connection.alias
    customers = Customer.objects.using(database).order_by("customer_number", "pk")
    next_by_category = {}
    for customer in customers.iterator():
        prefix = PREFIXES.get(customer.category)
        if prefix is None:
            # Uncategorized legacy customers keep their existing numeric identifier.
            customer.customer_number = str(customer.customer_number)
            customer.save(update_fields=("customer_number",), using=database)
            continue
        number = next_by_category.get(customer.category, 1)
        if number > 9999:
            raise RuntimeError(
                f"Cannot migrate more than 9999 customers in category {customer.category}"
            )
        customer.customer_number = f"{prefix}{number:02d}"
        customer.save(update_fields=("customer_number",), using=database)
        next_by_category[customer.category] = number + 1

    for category in (*PREFIXES, "uncategorized"):
        Sequence.objects.using(database).create(
            category=category, next_number=next_by_category.get(category, 1)
        )


class Migration(migrations.Migration):
    dependencies = [("crm", "0008_customernumbersequence_customer_customer_number_and_more")]

    operations = [
        migrations.RemoveConstraint(
            model_name="customer", name="customer_number_in_range"
        ),
        migrations.AlterField(
            model_name="customer",
            name="customer_number",
            field=models.CharField(
                editable=False, max_length=24, unique=True, verbose_name="شماره مشتری"
            ),
        ),
        migrations.RemoveField(
            model_name="customernumbersequence", name="next_number"
        ),
        migrations.AddField(
            model_name="customernumbersequence",
            name="category",
            field=models.CharField(default="uncategorized", max_length=20),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="customernumbersequence",
            name="category",
            field=models.CharField(max_length=20, unique=True),
        ),
        migrations.AddField(
            model_name="customernumbersequence",
            name="next_number",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.RunPython(categorize_existing_numbers, migrations.RunPython.noop),
    ]
