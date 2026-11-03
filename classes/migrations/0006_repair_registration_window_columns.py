from django.db import migrations


def add_missing_registration_columns(apps, schema_editor):
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        columns = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor,
                "classes_class",
            )
        }

    quote = connection.ops.quote_name

    statements = []

    if "registration_opens" not in columns:
        statements.append(
            f"ALTER TABLE {quote('classes_class')} "
            f"ADD COLUMN {quote('registration_opens')} date NULL"
        )

    if "registration_closes" not in columns:
        statements.append(
            f"ALTER TABLE {quote('classes_class')} "
            f"ADD COLUMN {quote('registration_closes')} date NULL"
        )

    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)


class Migration(migrations.Migration):

    dependencies = [
        (
            "classes",
            "0005_class_is_performance_class_class_registration_closes_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(
            add_missing_registration_columns,
            migrations.RunPython.noop,
        ),
    ]