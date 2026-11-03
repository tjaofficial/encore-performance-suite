from datetime import date, datetime
from decimal import Decimal

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError

from enrollments.models import Enrollment


SNAPSHOT_EXCLUDE_FIELDS = {
    "id",
    "pk",
    "created_at",
    "updated_at",
    "enrolled_at",
    "dropped_at",
    "waitlisted_at",
}


def snapshot_instance(instance):
    data = {}

    for field in instance._meta.concrete_fields:
        if field.name in SNAPSHOT_EXCLUDE_FIELDS:
            continue

        if field.is_relation:
            data[field.attname] = getattr(instance, field.attname)
            continue

        value = getattr(instance, field.name)

        if isinstance(value, (date, datetime)):
            value = value.isoformat()
        elif isinstance(value, Decimal):
            value = str(value)

        data[field.name] = value

    return data


def snapshot_matches(instance, snapshot):
    return snapshot_instance(instance) == (snapshot or {})


def resolve_import_object(row_result):
    if not row_result.object_type or not row_result.object_id:
        return None

    if "." not in row_result.object_type:
        return None

    app_label, model_name = row_result.object_type.split(".", 1)

    try:
        model = apps.get_model(app_label, model_name)
    except LookupError:
        return None

    try:
        return model.objects.get(pk=row_result.object_id)
    except model.DoesNotExist:
        return None


def _deserialize(field, value):
    if value is None:
        return None

    internal_type = field.get_internal_type()

    if internal_type == "DateField" and isinstance(value, str):
        return date.fromisoformat(value)

    if internal_type == "DateTimeField" and isinstance(value, str):
        return datetime.fromisoformat(value)

    if internal_type == "DecimalField":
        return Decimal(str(value))

    return value


def restore_snapshot(instance, snapshot):
    fields = {field.name: field for field in instance._meta.concrete_fields}
    attnames = {field.attname: field for field in instance._meta.concrete_fields}

    candidate = instance.__class__.objects.get(pk=instance.pk)

    for key, value in (snapshot or {}).items():
        field = attnames.get(key) or fields.get(key)

        if field is None:
            continue

        target = field.attname if key == field.attname else field.name
        setattr(candidate, target, _deserialize(field, value))

    candidate.full_clean()

    if isinstance(candidate, Enrollment):
        updates = {}
        for key, value in (snapshot or {}).items():
            field = attnames.get(key) or fields.get(key)
            if field is None:
                continue
            target = field.attname if key == field.attname else field.name
            updates[target] = _deserialize(field, value)

        Enrollment.objects.filter(pk=candidate.pk).update(**updates)
        candidate.refresh_from_db()
        return candidate

    candidate.save()
    return candidate


def created_record_has_dependencies(instance):
    label = instance._meta.label_lower

    if label == "families.family":
        if instance.students.exists():
            return "This family now has students attached to it."
        if instance.guardians.exists():
            return "This family now has guardians attached to it."

    if label == "students.student":
        if instance.enrollments.exists():
            return "This student now has enrollments attached to it."

    if label == "classes.class":
        if instance.enrollments.exists():
            return "This class now has enrollments attached to it."

    return ""


def safe_delete_created_record(instance):
    dependency = created_record_has_dependencies(instance)

    if dependency:
        return False, dependency

    try:
        instance.delete()
    except ProtectedError as exc:
        return False, f"Related records now depend on this record: {exc}"
    except Exception as exc:
        return False, f"Encore could not remove this record safely: {exc}"

    return True, "Created record removed."
