import csv
import io
import json
import re
import uuid
import zipfile
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.validators import validate_email
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.urls import reverse

from billing.models import Charge, Credit, FamilyAccount
from classes.models import Class, ClassLevel, ClassMeeting, ClassType, Season
from costumes.models import StudentMeasurementSet
from enrollments.models import Enrollment
from families.models import Family, Guardian
from communications.email_service import EncoreEmailError, send_email
from instructors.models import Instructor
from students.models import Student
from studios.models import (
    DataImportJob,
    DataImportRowResult,
    Studio,
    StudioMembership,
    StudioLocation,
    StudioRoom,
    VendorOnboardingRun,
)

from .data_transfer_history_services import (
    resolve_import_object,
    restore_snapshot,
    safe_delete_created_record,
    snapshot_instance,
    snapshot_matches,
)

from .data_transfer_services import (
    IMPORT_TYPES,
    analyze_import_rows,
    commit_import_result,
    auto_map_headers,
    csv_value,
    parse_csv_path,
    parse_csv_upload,
    required_mapping_errors,
)
from .studio_director import (
    STUDIO_DIRECTOR_STEPS,
    discover_class_types,
    discover_classes_and_meetings,
    discover_drop_history,
    discover_enrollments,
    discover_rooms,
    discover_seasons,
    discover_student_measurements,
    studio_director_mapping,
    studio_director_step,
)


SESSION_KEY = "encore_data_import"
BILLING_TRANSITION_SESSION_KEY = "encore_studio_director_billing_transition"


STUDIO_DIRECTOR_VENDOR = "studio_director"


def _studio_director_run(studio, user=None):
    run, _ = VendorOnboardingRun.objects.get_or_create(
        studio=studio,
        vendor=STUDIO_DIRECTOR_VENDOR,
        defaults={"started_by": user},
    )
    return run


def _studio_director_counts(run):
    state = run.step_state or {}
    completed = sum(
        1 for key in STUDIO_DIRECTOR_STEPS
        if (state.get(key) or {}).get("status") in ("completed", "skipped")
    )
    return completed, len(STUDIO_DIRECTOR_STEPS)


def _admin_workspace(request, studio):
    if request.user.is_superuser:
        return True

    return (
        request.session.get("encore_workspace_role") == "administrator"
        and request.session.get("encore_workspace_studio_slug") == studio.slug
        and request.user.studio_memberships.filter(
            studio=studio,
            role="administrator",
            is_active=True,
        ).exists()
    )




def _tour_context(request, studio):
    membership = (
        request.user.studio_memberships
        .filter(
            studio=studio,
            role=StudioMembership.Role.ADMINISTRATOR,
            is_active=True,
        )
        .first()
    )
    if membership is None:
        return {
            "encore_tour_active": False,
            "encore_tour_status": "",
            "encore_tour_step": 0,
        }

    active = membership.onboarding_tour_status in {
        StudioMembership.TourStatus.NOT_STARTED,
        StudioMembership.TourStatus.IN_PROGRESS,
    }
    return {
        "encore_tour_active": active,
        "encore_tour_status": membership.onboarding_tour_status,
        "encore_tour_step": membership.onboarding_tour_step,
    }


def _deny(request, studio):
    return render(
        request,
        "dashboard/access_denied.html",
        {"studio": studio},
        status=403,
    )


def _staging_root(studio):
    root = Path(settings.MEDIA_ROOT) / "import_staging" / str(studio.pk)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _remove_staged_file(state, studio):
    if not state:
        return
    raw_path = state.get("staged_path")
    if not raw_path:
        return

    try:
        path = Path(raw_path).resolve()
        root = _staging_root(studio).resolve()
        path.relative_to(root)
    except (ValueError, OSError):
        return

    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _staged_path_from_state(state, studio):
    raw_path = state.get("staged_path") if state else None
    if not raw_path:
        return None

    try:
        path = Path(raw_path).resolve()
        root = _staging_root(studio).resolve()
        path.relative_to(root)
    except (ValueError, OSError):
        return None

    return path if path.exists() else None


@login_required
def data_transfer_home(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    recent_jobs = DataImportJob.objects.filter(studio=studio).select_related("created_by")[:8]
    studio_director_run = VendorOnboardingRun.objects.filter(
        studio=studio,
        vendor=STUDIO_DIRECTOR_VENDOR,
    ).first()
    studio_director_completed, studio_director_total = (
        _studio_director_counts(studio_director_run)
        if studio_director_run
        else (0, len(STUDIO_DIRECTOR_STEPS))
    )

    return render(
        request,
        "studios/data_transfer_home.html",
        {
            "studio": studio,
            "role": "administrator",
            "settings_section": "data_transfer",
            "import_types": IMPORT_TYPES,
            "recent_jobs": recent_jobs,
            "studio_director_run": studio_director_run,
            "studio_director_completed": studio_director_completed,
            "studio_director_total": studio_director_total,
            **_tour_context(request, studio),
        },
    )


@login_required
def studio_director_onboarding(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    run = _studio_director_run(studio, request.user)
    if request.method == "POST" and request.POST.get("action") == "skip_special_class_tuition":
        state = dict(run.step_state or {})
        if (state.get("special_class_tuition") or {}).get("status") != "completed":
            state["special_class_tuition"] = {
                "status": "skipped", "completed_at": timezone.now().isoformat(),
                "completed_by": request.user.pk,
            }
            run.step_state = state
            run.save(update_fields=["step_state", "updated_at"])
            messages.success(request, "Class review skipped. No class settings were changed.")
        return redirect("studios:studio_director_onboarding", studio_slug=studio.slug)
    completed, total = _studio_director_counts(run)
    state = run.step_state or {}

    steps = []
    for key, config in STUDIO_DIRECTOR_STEPS.items():
        item = dict(config)
        item["key"] = key
        item["state"] = state.get(key, {})
        item["is_complete"] = item["state"].get("status") in ("completed", "skipped")
        steps.append(item)

    for item in steps:
        link_name = item.get("settings_link_name")
        if link_name:
            try:
                item["settings_url"] = reverse(link_name, kwargs={"studio_slug": studio.slug})
            except Exception:
                item["settings_url"] = ""

        if item.get("key") == "instructor_activation":
            item["instructor_activation_url"] = reverse(
                "studios:studio_director_instructor_activation",
                kwargs={"studio_slug": studio.slug},
            )

        if item.get("key") == "billing_transition":
            item["billing_transition_url"] = reverse(
                "studios:studio_director_billing_transition",
                kwargs={"studio_slug": studio.slug},
            )

        if item.get("key") == "billing_activation":
            item["billing_activation_url"] = reverse(
                "studios:studio_director_billing_activation",
                kwargs={"studio_slug": studio.slug},
            )

        if item.get("key") == "final_review":
            item["review_url"] = reverse(
                "studios:studio_director_final_review",
                kwargs={"studio_slug": studio.slug},
            )

    return render(
        request,
        "studios/studio_director_onboarding.html",
        {
            "studio": studio,
            "role": "administrator",
            "settings_section": "data_transfer",
            "run": run,
            "steps": steps,
            "completed": completed,
            "total": total,
        },
    )


@login_required
def studio_director_instructor_activation(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    run = _studio_director_run(
        studio,
        request.user,
    )

    instructors = list(
        Instructor.objects
        .filter(studio=studio)
        .select_related("user")
        .order_by("last_name", "first_name")
    )

    if request.method == "POST":
        selected_ids = {
            int(value)
            for value in request.POST.getlist(
                "instructor_ids"
            )
            if str(value).isdigit()
        }

        selected = [
            instructor
            for instructor in instructors
            if instructor.pk in selected_ids
        ]

        if not selected:
            messages.error(
                request,
                "Choose at least one instructor to activate.",
            )
        else:
            sent = 0
            failed = []

            for instructor in selected:
                email = str(
                    instructor.email or ""
                ).strip()

                try:
                    validate_email(email)
                except ValidationError:
                    failed.append(
                        f"{instructor.full_name}: missing or invalid email"
                    )
                    continue

                if (
                    instructor.claimed_at
                    and instructor.user_id
                ):
                    continue

                instructor.activation_token = uuid.uuid4()
                instructor.activation_sent_at = timezone.now()
                instructor.activation_expires_at = (
                    timezone.now()
                    + timedelta(days=7)
                )
                instructor.is_active = True
                instructor.save(
                    update_fields=[
                        "activation_token",
                        "activation_sent_at",
                        "activation_expires_at",
                        "is_active",
                        "updated_at",
                    ]
                )

                claim_url = request.build_absolute_uri(
                    reverse(
                        "instructors:instructor_claim_profile",
                        kwargs={
                            "activation_token": instructor.activation_token,
                        },
                    )
                )

                html_body = (
                    f"<p>Hello {instructor.first_name or 'Instructor'},</p>"
                    f"<p>{studio.name} has activated your Encore instructor profile.</p>"
                    "<p>Please use the secure link below to review your profile, "
                    "create or connect your Encore login, and submit your weekly "
                    "teaching availability.</p>"
                    f'<p><a href="{claim_url}">Claim your instructor profile</a></p>'
                    "<p>This link expires in 7 days.</p>"
                )

                try:
                    send_email(
                        to=[email],
                        subject=(
                            f"Activate your {studio.name} instructor profile"
                        ),
                        html_body=html_body,
                        text_body=(
                            f"{studio.name} has activated your Encore instructor profile.\n\n"
                            f"Claim your profile: {claim_url}\n\n"
                            "This link expires in 7 days."
                        ),
                        tags={
                            "message_type": "instructor_activation",
                            "studio_id": studio.pk,
                        },
                    )
                except EncoreEmailError as exc:
                    instructor.is_active = False
                    instructor.save(
                        update_fields=[
                            "is_active",
                            "updated_at",
                        ]
                    )
                    failed.append(
                        f"{instructor.full_name}: {exc}"
                    )
                else:
                    sent += 1

            run_state = dict(
                run.step_state or {}
            )
            run_state["instructor_activation"] = {
                "status": "completed",
                "activated": len(selected),
                "emails_sent": sent,
                "failed": len(failed),
                "completed_at": timezone.now().isoformat(),
            }
            run.step_state = run_state
            run.save(
                update_fields=[
                    "step_state",
                    "updated_at",
                ]
            )

            if sent:
                messages.success(
                    request,
                    f"{sent} instructor activation email"
                    f"{'' if sent == 1 else 's'} sent.",
                )

            if failed:
                messages.error(
                    request,
                    "Some instructors could not be activated: "
                    + "; ".join(failed[:8]),
                )

            return redirect(
                "studios:studio_director_instructor_activation",
                studio_slug=studio.slug,
            )

    return render(
        request,
        "studios/studio_director_instructor_activation.html",
        {
            "studio": studio,
            "role": "administrator",
            "settings_section": "data_transfer",
            "instructors": instructors,
            "activation_state": (
                (run.step_state or {}).get(
                    "instructor_activation",
                    {},
                )
            ),
        },
    )


@login_required
def studio_director_vocabulary(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )
    if not _admin_workspace(
        request,
        studio,
    ):
        return _deny(
            request,
            studio,
        )

    run = _studio_director_run(
        studio,
        request.user,
    )
    state = dict(
        run.step_state
        or {}
    )
    vocabulary_state = dict(
        state.get(
            "import_vocabulary",
        )
        or {}
    )
    rules = list(
        vocabulary_state.get(
            "rules",
        )
        or []
    )

    if request.method == "POST":
        try:
            submitted = json.loads(
                request.POST.get(
                    "rules_json",
                    "[]",
                )
            )
        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            submitted = []

        if not isinstance(
            submitted,
            list,
        ):
            submitted = []

        cleaned_rules = []
        for item in submitted:
            if not isinstance(
                item,
                dict,
            ):
                continue

            term = str(
                item.get("term")
                or ""
            ).strip()
            if not term:
                continue

            def decimal_text(value):
                raw = str(
                    value
                    or ""
                ).strip()
                if not raw:
                    return ""
                try:
                    parsed = Decimal(raw)
                except (
                    InvalidOperation,
                    ValueError,
                ):
                    return ""
                if parsed < 0:
                    return ""
                return format(
                    parsed.normalize(),
                    "f",
                )

            performance = str(
                item.get("performance")
                or ""
            ).strip().lower()
            if performance not in {
                "",
                "yes",
                "no",
            }:
                performance = ""

            registration = str(
                item.get("registration")
                or ""
            ).strip().lower()
            if registration not in {
                "",
                "open",
                "closed",
            }:
                registration = ""

            level_id = str(
                item.get("level_id")
                or ""
            ).strip()
            if not (
                level_id.isdigit()
                and ClassLevel.objects.filter(
                    studio=studio,
                    pk=int(level_id),
                    is_active=True,
                ).exists()
            ):
                level_id = ""

            class_type_id = str(
                item.get("class_type_id")
                or ""
            ).strip()
            if not (
                class_type_id.isdigit()
                and ClassType.objects.filter(
                    studio=studio,
                    pk=int(class_type_id),
                ).exists()
            ):
                class_type_id = ""

            cleaned_rules.append(
                {
                    "term": term,
                    "min_age": decimal_text(
                        item.get("min_age")
                    ),
                    "max_age": decimal_text(
                        item.get("max_age")
                    ),
                    "level_id": level_id,
                    "class_type_id": (
                        class_type_id
                    ),
                    "class_type_suffix": str(
                        item.get(
                            "class_type_suffix"
                        )
                        or ""
                    ).strip(),
                    "performance": (
                        performance
                    ),
                    "registration": (
                        registration
                    ),
                }
            )

        vocabulary_state["rules"] = (
            cleaned_rules
        )
        vocabulary_state[
            "updated_at"
        ] = timezone.now().isoformat()
        state[
            "import_vocabulary"
        ] = vocabulary_state
        run.step_state = state
        run.save(
            update_fields=[
                "step_state",
                "updated_at",
            ]
        )

        messages.success(
            request,
            "Studio Director import vocabulary saved.",
        )

        return redirect(
            "studios:studio_director_vocabulary",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "studios/studio_director_vocabulary.html",
        {
            "studio": studio,
            "role": "administrator",
            "settings_section": "data_transfer",
            "run": run,
            "rules": rules,
            "rules_json": json.dumps(
                rules
            ),
            "class_levels": (
                ClassLevel.objects
                .filter(
                    studio=studio,
                    is_active=True,
                )
                .order_by(
                    "number",
                    "name",
                )
            ),
            "class_types": (
                ClassType.objects
                .filter(
                    studio=studio,
                    is_active=True,
                )
                .order_by(
                    "name",
                )
            ),
        },
    )


# A class naming template is a sequence of field tokens and literal separators.
# The same renderer is used by discovery previews and the final commit.
_CLASS_NAME_TOKENS = {"SOURCE_NAME", "TYPE", "LEVEL_NAME", "LEVEL_NUMBER", "AGE_GROUP"}
_CLASS_NAME_DEFAULT = "{TYPE} - {LEVEL_NAME}"


def _valid_class_name_template(value):
    import re
    value = str(value or "").strip()
    if not value or len(value) > 180:
        return False
    tokens = re.findall(r"\{([^{}]+)\}", value)
    if not tokens or any(token not in _CLASS_NAME_TOKENS for token in tokens):
        return False
    remainder = re.sub(r"\{[^{}]+\}", "", value)
    return "{" not in remainder and "}" not in remainder


def _render_class_name(template, proposal, *, class_type=None, level=None):
    import re
    values = {
        "SOURCE_NAME": str(proposal.get("source_name") or proposal.get("name") or "").strip(),
        "TYPE": str(class_type.name if class_type is not None else (proposal.get("_resolved_class_type_name") or proposal.get("class_type_name") or proposal.get("class_type_suggested_name") or "")).strip(),
        "LEVEL_NAME": str(level.name if level is not None else (proposal.get("level_name") or "")).strip(),
        "LEVEL_NUMBER": str(level.number if level is not None else (proposal.get("level_number") or "")).strip(),
    }
    low, high = proposal.get("min_age"), proposal.get("max_age")
    def age_label(value):
        if value is None or str(value).strip() == "":
            return ""
        from decimal import Decimal, InvalidOperation
        try:
            decimal = Decimal(str(value))
            return str(int(decimal)) if decimal == decimal.to_integral_value() else format(decimal.normalize(), "f")
        except (InvalidOperation, ValueError):
            return str(value)
    low, high = age_label(low), age_label(high)
    values["AGE_GROUP"] = (f"{low}–{high}" if low and high else
                           f"{low}+" if low else f"Up to {high}" if high else "")
    if not _valid_class_name_template(template):
        return values["SOURCE_NAME"]
    result = re.sub(r"\{([^{}]+)\}", lambda match: values.get(match.group(1), ""), template)
    result = re.sub(r"\s+", " ", result).strip(" -/|_,")
    # Missing fields must never silently turn a valid source name into a blank title.
    return result[:255] if result else values["SOURCE_NAME"][:255]


@login_required
def studio_director_step_upload(request, studio_slug, step_key):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    step = studio_director_step(step_key)
    if not step:
        raise Http404("Unknown Studio Director onboarding step.")

    run = _studio_director_run(studio, request.user)

    if step.get("manual") or step.get("coming_next"):
        messages.info(
            request,
            "This Studio Director step is not file-driven yet.",
        )
        return redirect("studios:studio_director_onboarding", studio_slug=studio.slug)

    import_type = step.get("import_type")

    if request.method == "POST" and step_key == "classes_meetings" and not _valid_class_name_template(
        request.POST.get("class_name_template", _CLASS_NAME_DEFAULT)
    ):
        messages.error(request, "Use valid class-name fields, such as {TYPE} - {LEVEL_NAME}.")
        return redirect("studios:studio_director_step_upload", studio_slug=studio.slug, step_key=step_key)

    if request.method == "POST":
        uploaded_file = request.FILES.get("csv_file")
        if uploaded_file is None:
            messages.error(request, "Choose the Studio Director CSV for this step.")
        elif not uploaded_file.name.lower().endswith(".csv"):
            messages.error(request, "Studio Director onboarding currently accepts CSV files.")
        elif uploaded_file.size > 10 * 1024 * 1024:
            messages.error(request, "CSV files must be 10 MB or smaller.")
        else:
            try:
                parsed = parse_csv_upload(uploaded_file)
            except UnicodeDecodeError:
                messages.error(request, "Encore could not read that file as UTF-8 CSV data.")
            except (csv.Error, ValueError) as exc:
                messages.error(request, str(exc))
            else:
                old_state = request.session.get(SESSION_KEY)
                _remove_staged_file(old_state, studio)

                staged_path = _staging_root(studio) / f"{uuid.uuid4().hex}.csv"
                staged_path.write_text(parsed["text"], encoding="utf-8-sig")

                request.session[SESSION_KEY] = {
                    "filename": uploaded_file.name,
                    "import_type": import_type,
                    "headers": parsed["headers"],
                    "preview_rows": parsed["preview_rows"],
                    "total_rows": parsed["total_rows"],
                    "mapping": (
                        studio_director_mapping(parsed["headers"], step_key)
                        if import_type
                        else {}
                    ),
                    "staged_path": str(staged_path),
                    "vendor": STUDIO_DIRECTOR_VENDOR,
                    "vendor_step": step_key,
                    "vendor_run_id": run.pk,
                    "class_name_template": (
                        request.POST.get("class_name_template", _CLASS_NAME_DEFAULT).strip()
                        if step_key == "classes_meetings" else ""
                    ),
                }
                request.session.modified = True

                if step.get("discovery"):
                    return redirect(
                        "studios:studio_director_discovery_review",
                        studio_slug=studio.slug,
                        step_key=step_key,
                    )

                return redirect("studios:data_import_map", studio_slug=studio.slug)

    return render(
        request,
        "studios/studio_director_step_upload.html",
        {
            "studio": studio,
            "role": "administrator",
            "settings_section": "data_transfer",
            "run": run,
            "step": {**step, "key": step_key},
            "class_name_default": (
                (run.step_state or {}).get("class_name_pattern") or _CLASS_NAME_DEFAULT
            ),
        },
    )


def _vendor_discovery_analysis(studio, step_key, rows, *, extra_rules=None):
    if step_key == "student_measurements":
        return {"proposals": discover_student_measurements(studio, rows), "meta": {}}
    if step_key == "locations_rooms":
        return {"proposals": discover_rooms(studio, rows), "meta": {}}
    if step_key == "seasons":
        return {"proposals": discover_seasons(studio, rows), "meta": {}}
    if step_key == "class_types":
        proposals, unresolved = discover_class_types(studio, rows)
        return {"proposals": proposals, "meta": {"unresolved": unresolved}}
    if step_key == "classes_meetings":
        return {"proposals": discover_classes_and_meetings(studio, rows, extra_rules=extra_rules), "meta": {}}
    if step_key == "enrollments":
        return {"proposals": discover_enrollments(studio, rows), "meta": {}}
    if step_key == "drop_history":
        return {"proposals": discover_drop_history(studio, rows), "meta": {}}
    raise Http404("Unknown Studio Director discovery step.")


def _create_vendor_job(studio, user, step_key, filename, total):
    return DataImportJob.objects.create(
        studio=studio,
        created_by=user,
        import_type=f"studio_director_{step_key}",
        original_filename=filename,
        total_rows=total,
    )


def _finish_vendor_job(job, created, updated, skipped, errors):
    job.created_count = created
    job.updated_count = updated
    job.skipped_count = skipped
    job.error_count = errors
    job.failed_count = 0
    job.completed_at = timezone.now()
    job.status = (
        DataImportJob.Status.COMPLETED_WITH_ISSUES
        if errors
        else DataImportJob.Status.COMPLETED
    )
    job.save()


def _record_vendor_step_complete(run, step_key, job):
    state = dict(run.step_state or {})
    state[step_key] = {
        "status": "completed",
        "job_id": job.pk,
        "filename": job.original_filename,
        "created": job.created_count,
        "updated": job.updated_count,
        "not_imported": job.not_imported_count,
        "completed_at": timezone.now().isoformat(),
    }
    run.step_state = state
    run.save(update_fields=["step_state", "updated_at"])


@login_required
def studio_director_discovery_review(request, studio_slug, step_key):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    step = studio_director_step(step_key)
    if not step or not step.get("discovery"):
        raise Http404("Unknown Studio Director discovery step.")

    state = request.session.get(SESSION_KEY)
    if (
        not state
        or state.get("vendor") != STUDIO_DIRECTOR_VENDOR
        or state.get("vendor_step") != step_key
    ):
        messages.info(request, "Upload the Studio Director report for this step first.")
        return redirect(
            "studios:studio_director_step_upload",
            studio_slug=studio.slug,
            step_key=step_key,
        )

    staged_path = _staged_path_from_state(state, studio)
    if staged_path is None:
        messages.warning(request, "That staged CSV is no longer available. Upload the file again.")
        return redirect(
            "studios:studio_director_step_upload",
            studio_slug=studio.slug,
            step_key=step_key,
        )

    try:
        parsed = parse_csv_path(staged_path)
    except (UnicodeDecodeError, csv.Error, ValueError, OSError) as exc:
        messages.error(request, f"Encore could not re-read the staged CSV: {exc}")
        return redirect(
            "studios:studio_director_step_upload",
            studio_slug=studio.slug,
            step_key=step_key,
        )

    if step_key == "classes_meetings" and request.method == "POST":
        action = request.POST.get("review_action")
        if action == "start_fresh":
            state.pop("class_review_translations", None)
            request.session[SESSION_KEY] = state
            request.session.modified = True
            messages.info(request, "Review reset. Original CSV analyzed without temporary translations.")
            return redirect("studios:studio_director_discovery_review", studio_slug=studio.slug, step_key=step_key)
        if action == "apply_translations":
            import re
            try:
                items = json.loads(request.POST.get("translation_rules_json") or "[]")
                if not isinstance(items, list) or len(items) > 30:
                    raise ValueError("Provide up to 30 translation rules.")
                clean = []
                for item in items:
                    if not isinstance(item, dict):
                        raise ValueError("Invalid translation rule.")
                    terms = [x.strip() for x in str(item.get("terms") or "").split(",") if x.strip()]
                    if not terms or len(terms) > 12 or any(len(x)>80 for x in terms):
                        raise ValueError("Each rule requires 1–12 terms (80 characters maximum each).")
                    field = item.get("field")
                    value = str(item.get("value") or "").strip()
                    if field == "age_range":
                        match = re.fullmatch(r"(\d{1,2})\s*[-–]\s*(\d{1,2})", value)
                        if not match or int(match.group(1)) > int(match.group(2)) or int(match.group(2)) > 99:
                            raise ValueError("Age group must look like 3-5.")
                        effects = {"min_age": str(int(match.group(1))), "max_age": str(int(match.group(2)))}
                    elif field in {"class_type_id", "level_id"}:
                        if not value.isdigit():
                            raise ValueError("Choose a valid class type or level.")
                        model = ClassType if field == "class_type_id" else ClassLevel
                        if not model.objects.filter(studio=studio, pk=int(value), **({} if field == "class_type_id" else {"is_active": True})).exists():
                            raise ValueError("The selected class type or level does not belong to this studio.")
                        effects = {field: value}
                    elif field == "class_type_suffix":
                        if not value or len(value) > 60:
                            raise ValueError("Class type suffix must contain 1–60 characters.")
                        effects = {"class_type_suffix": value}
                    elif field == "performance":
                        if value not in {"yes", "no"}:
                            raise ValueError("Choose Yes or No for performance.")
                        effects = {"performance": value}
                    elif field == "registration":
                        if value not in {"open", "closed"}:
                            raise ValueError("Choose Open or Closed for registration.")
                        effects = {"registration": value}
                    else:
                        raise ValueError("Unsupported translation field.")
                    for term in terms:
                        clean.append({"term": term, **effects})
                state["class_review_translations"] = {"entries": items, "rules": clean}
                request.session[SESSION_KEY] = state
                request.session.modified = True
                messages.success(request, "Translations applied to the import preview. No classes were saved.")
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                messages.error(request, str(exc))
            return redirect("studios:studio_director_discovery_review", studio_slug=studio.slug, step_key=step_key)

    extra_rules = (state.get("class_review_translations") or {}).get("rules", []) if step_key == "classes_meetings" else []
    analysis = _vendor_discovery_analysis(studio, step_key, parsed["rows"], extra_rules=extra_rules)
    proposals = analysis["proposals"]
    class_name_template = state.get("class_name_template") or _CLASS_NAME_DEFAULT
    if step_key == "class_types":
        existing_types = {item.pk: item for item in ClassType.objects.filter(studio=studio)}
        for proposal in proposals:
            existing = existing_types.get(proposal.get("object_id"))
            proposal["review_is_active"] = existing.is_active if existing else True
    if step_key == "classes_meetings":
        for proposal in proposals:
            proposal["preview_name"] = _render_class_name(class_name_template, proposal)

    counts = {
        "total": len(proposals),
        "create": sum(1 for item in proposals if item.get("status") == "create"),
        "update": sum(1 for item in proposals if item.get("status") == "update"),
        "skip": sum(1 for item in proposals if item.get("status") == "skip"),
        "error": sum(1 for item in proposals if item.get("status") == "error"),
    }

    return render(
        request,
        "studios/studio_director_discovery_review.html",
        {
            "studio": studio,
            "role": "administrator",
            "settings_section": "data_transfer",
            "step": {**step, "key": step_key},
            "state": state,
            "proposals": proposals,
            "class_name_template": class_name_template,
            "class_review_translations": (state.get("class_review_translations") or {}).get("entries", []),
            "counts": counts,
            "meta": analysis["meta"],
            "physical_locations": StudioLocation.objects.filter(
                studio=studio,
                is_active=True,
            ).order_by("-is_primary", "name"),
            "instructors": Instructor.objects.filter(
                studio=studio,
                is_active=True,
            ).order_by("last_name", "first_name"),
            "seasons": Season.objects.filter(
                studio=studio,
            ).order_by("-start_date", "name"),
            "class_types": ClassType.objects.filter(
                studio=studio,
            ).order_by("name"),
            "class_levels": ClassLevel.objects.filter(
                studio=studio,
                is_active=True,
            ).order_by("number", "name"),
        },
    )



def _truthy_post(request, name):
    return str(request.POST.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _remove_resolution_error(errors, kind):
    cleaned = []
    for error in errors or []:
        text = str(error or "")
        if kind == "season" and text.startswith('Season "') and "could not be resolved" in text:
            continue
        if kind == "class_type" and text.startswith("Class type could not be resolved"):
            continue
        if kind == "split" and text.startswith("Multiple class types were detected"):
            continue
        if kind == "instructor" and (
            text.startswith('Instructor initials "')
            or text.startswith('No unique Encore instructor matches')
            or text.startswith('No unique Encore instructor')
        ):
            continue
        cleaned.append(text)
    return cleaned


def _auxiliary_import_result(job, row_number, obj, label):
    return DataImportRowResult(
        job=job,
        row_number=row_number,
        status=DataImportRowResult.Status.CREATED,
        label=label,
        reason="Created while resolving Classes + Meetings onboarding review.",
        source_data={"created_during": "studio_director_classes_meetings_resolution"},
        normalized_data={},
        object_type=obj._meta.label_lower,
        object_id=str(obj.pk),
        was_created=True,
        before_data={},
        after_data=_jsonable(snapshot_instance(obj)),
    )


def _prepare_class_meeting_resolutions(request, studio, proposals, job):
    """Resolve/create missing seasons, instructors, and class types before class commit."""
    aux_results = []
    aux_row = 100000

    try:
        raw_resolutions = json.loads(request.POST.get("resolutions_json", "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        raw_resolutions = {}

    if not isinstance(raw_resolutions, dict):
        raw_resolutions = {}

    season_apply = {}
    instructor_apply = {}
    class_type_apply = {}
    submitted = {}

    # Classes + Meetings can contain thousands of rows. Resolution controls are
    # intentionally posted as one JSON field so Django does not have to parse
    # thousands of individual POST parameters.
    for proposal in proposals:
        suffix = str(proposal["class_id"])
        source = raw_resolutions.get(suffix) or {}
        if not isinstance(source, dict):
            source = {}

        season_source = source.get("season") or {}
        instructor_source = source.get("instructor") or {}
        class_type_source = source.get("class_type") or {}
        split_source = source.get("split") or {}
        edit_source = source.get("edit") or {}
        if not isinstance(edit_source, dict):
            edit_source = {}

        if not isinstance(season_source, dict):
            season_source = {}
        if not isinstance(instructor_source, dict):
            instructor_source = {}
        if not isinstance(class_type_source, dict):
            class_type_source = {}
        if not isinstance(split_source, dict):
            split_source = {}

        row = {
            "season": {
                "name": str(
                    season_source.get("name", proposal.get("season_raw", ""))
                    or ""
                ).strip(),
                "start": str(
                    season_source.get("start", proposal.get("season_suggested_start", ""))
                    or ""
                ).strip(),
                "end": str(
                    season_source.get("end", proposal.get("season_suggested_end", ""))
                    or ""
                ).strip(),
            },
            "instructor": {
                "action": str(instructor_source.get("action", "") or "").strip(),
                "existing": str(instructor_source.get("existing", "") or "").strip(),
                "first": str(instructor_source.get("first", "") or "").strip(),
                "last": str(instructor_source.get("last", "") or "").strip(),
                "email": str(instructor_source.get("email", "") or "").strip(),
            },
            "class_type": {
                "action": str(class_type_source.get("action", "") or "").strip(),
                "existing": str(class_type_source.get("existing", "") or "").strip(),
                "name": str(
                    class_type_source.get(
                        "name",
                        proposal.get("class_type_suggested_name", ""),
                    )
                    or ""
                ).strip(),
            },
            "split": {
                key: str(value or "").strip()
                for key, value in split_source.items()
                if key not in {"group", "apply_all"}
            },
        }
        row["edit"] = edit_source
        submitted[suffix] = row

        if bool(season_source.get("apply_all")):
            group = (
                season_source.get("group")
                or proposal.get("season_group")
                or proposal.get("season_raw")
                or suffix
            )
            season_apply[str(group)] = dict(row["season"])

        if bool(instructor_source.get("apply_all")):
            group = (
                instructor_source.get("group")
                or proposal.get("instructor_group")
                or proposal.get("instructor_raw")
                or suffix
            )
            instructor_apply[str(group)] = dict(row["instructor"])

        if bool(class_type_source.get("apply_all")):
            group = (
                class_type_source.get("group")
                or proposal.get("class_type_group")
                or suffix
            )
            class_type_apply[str(group)] = dict(row["class_type"])

    season_cache = {}
    instructor_cache = {}
    class_type_cache = {}

    for proposal in proposals:
        suffix = str(proposal["class_id"])
        errors = list(proposal.get("errors") or [])
        row = submitted[suffix]

        # ---------- Season ----------
        if proposal.get("season_id"):
            proposal["_resolved_season_id"] = proposal["season_id"]
        else:
            season_data = season_apply.get(proposal.get("season_group"), row["season"])
            season_name = season_data.get("name", "").strip()
            season_obj = None
            season_error = ""
            if season_name:
                season_obj = Season.objects.filter(studio=studio, name__iexact=season_name).first()
                if season_obj is None:
                    cache_key = season_name.lower()
                    season_obj = season_cache.get(cache_key)
                    if season_obj is None:
                        try:
                            start_date = datetime.fromisoformat(season_data.get("start") or "").date()
                            end_date = datetime.fromisoformat(season_data.get("end") or "").date()
                            season_obj = Season(
                                studio=studio,
                                name=season_name,
                                start_date=start_date,
                                end_date=end_date,
                                is_active=end_date >= timezone.localdate(),
                                registration_open=False,
                            )
                            season_obj.full_clean()
                            season_obj.save()
                            season_cache[cache_key] = season_obj
                            aux_results.append(_auxiliary_import_result(
                                job, aux_row, season_obj, f"Season: {season_obj.name}"
                            ))
                            aux_row += 1
                        except Exception as exc:
                            season_error = f'Season "{season_name}" could not be created: {exc}'
            else:
                season_error = "Choose or enter a season name."

            if season_obj is not None:
                proposal["_resolved_season_id"] = season_obj.pk
                proposal["_resolved_season_name"] = season_obj.name
                errors = _remove_resolution_error(errors, "season")
            else:
                errors = _remove_resolution_error(errors, "season")
                errors.append(season_error or "Season could not be resolved.")

        # ---------- Instructor ----------
        if proposal.get("instructor_id"):
            proposal["_resolved_instructor_id"] = proposal["instructor_id"]
        else:
            instructor_data = instructor_apply.get(proposal.get("instructor_group"), row["instructor"])
            instructor_obj = None
            instructor_error = ""
            action = instructor_data.get("action")
            if action == "existing" and instructor_data.get("existing"):
                instructor_obj = Instructor.objects.filter(
                    studio=studio,
                    pk=instructor_data["existing"],
                    is_active=True,
                ).first()
                if instructor_obj is None:
                    instructor_error = "The selected instructor could not be found."
            elif action == "new":
                first = instructor_data.get("first", "").strip()
                last = instructor_data.get("last", "").strip()
                email = instructor_data.get("email", "").strip()
                if first and last:
                    cache_key = (first.lower(), last.lower(), email.lower())
                    instructor_obj = instructor_cache.get(cache_key)
                    if instructor_obj is None:
                        instructor_obj = Instructor.objects.filter(
                            studio=studio,
                            first_name__iexact=first,
                            last_name__iexact=last,
                        ).first()
                    if instructor_obj is None:
                        try:
                            instructor_obj = Instructor(
                                studio=studio,
                                first_name=first,
                                last_name=last,
                                email=email,
                                phone="",
                                is_active=True,
                            )
                            instructor_obj.full_clean()
                            instructor_obj.save()
                            instructor_cache[cache_key] = instructor_obj
                            aux_results.append(_auxiliary_import_result(
                                job, aux_row, instructor_obj, f"Instructor: {instructor_obj.full_name}"
                            ))
                            aux_row += 1
                        except Exception as exc:
                            instructor_obj = None
                            instructor_error = f"Instructor could not be created: {exc}"
                else:
                    instructor_error = "First and last name are required to add a new instructor."
            else:
                instructor_error = "Choose an existing instructor or add a new instructor."

            if instructor_obj is not None:
                proposal["_resolved_instructor_id"] = instructor_obj.pk
                proposal["_resolved_instructor_name"] = instructor_obj.full_name
                errors = _remove_resolution_error(errors, "instructor")
            else:
                errors = _remove_resolution_error(errors, "instructor")
                errors.append(instructor_error)

        # ---------- Class Type ----------
        if proposal.get("class_type_id"):
            proposal["_resolved_class_type_id"] = proposal["class_type_id"]
        else:
            type_data = class_type_apply.get(proposal.get("class_type_group"), row["class_type"])
            type_obj = None
            type_error = ""
            action = type_data.get("action")
            if action == "existing" and type_data.get("existing"):
                type_obj = ClassType.objects.filter(
                    studio=studio,
                    pk=type_data["existing"],
                ).first()
                if type_obj is None:
                    type_error = "The selected class type could not be found."
            elif action == "new":
                name = type_data.get("name", "").strip()
                if name:
                    cache_key = name.lower()
                    type_obj = class_type_cache.get(cache_key)
                    if type_obj is None:
                        type_obj = ClassType.objects.filter(studio=studio, name__iexact=name).first()
                    if type_obj is None:
                        try:
                            type_obj = ClassType(studio=studio, name=name, is_active=True)
                            type_obj.full_clean()
                            type_obj.save()
                            class_type_cache[cache_key] = type_obj
                            aux_results.append(_auxiliary_import_result(
                                job, aux_row, type_obj, f"Class Type: {type_obj.name}"
                            ))
                            aux_row += 1
                        except Exception as exc:
                            type_obj = None
                            type_error = f"Class type could not be created: {exc}"
                else:
                    type_error = "Enter a name for the new class type."
            else:
                type_error = "Choose an existing class type or add a new class type."

            if type_obj is not None:
                proposal["_resolved_class_type_id"] = type_obj.pk
                proposal["_resolved_class_type_name"] = type_obj.name
                errors = _remove_resolution_error(errors, "class_type")
            else:
                errors = _remove_resolution_error(errors, "class_type")
                errors.append(type_error)

        # ---------- Multiple class-type split ----------
        if proposal.get("requires_split_review"):
            split_data = row.get("split") or {}
            split_action = (
                split_data.get("action")
                or ""
            ).strip().lower()

            if split_action == "keep":
                keep_type_id = str(
                    split_data.get(
                        "keep_class_type_id",
                    )
                    or ""
                ).strip()

                keep_level_id = str(
                    split_data.get(
                        "keep_level_id",
                    )
                    or ""
                ).strip()

                keep_type = None
                keep_level = None

                if keep_type_id.isdigit():
                    keep_type = (
                        ClassType.objects
                        .filter(
                            studio=studio,
                            pk=int(keep_type_id),
                            is_active=True,
                        )
                        .first()
                    )

                if keep_type is None:
                    errors = _remove_resolution_error(
                        errors,
                        "split",
                    )
                    errors.append(
                        "Choose a class type when keeping "
                        "this as one Encore class."
                    )
                else:
                    if keep_level_id == "none":
                        keep_level = None
                    elif keep_level_id.isdigit():
                        keep_level = (
                            ClassLevel.objects
                            .filter(
                                studio=studio,
                                pk=int(keep_level_id),
                                is_active=True,
                            )
                            .first()
                        )
                        if keep_level is None:
                            errors = _remove_resolution_error(
                                errors,
                                "split",
                            )
                            errors.append(
                                "Choose a valid level, or explicitly choose No level."
                            )
                    else:
                        errors = _remove_resolution_error(
                            errors,
                            "split",
                        )
                        errors.append(
                            "Choose a level, or explicitly choose No level."
                        )

                if (
                    keep_type is not None
                    and (
                        keep_level_id == "none"
                        or keep_level is not None
                    )
                ):
                    proposal[
                        "_resolved_class_type_id"
                    ] = keep_type.pk
                    proposal[
                        "_resolved_class_type_name"
                    ] = keep_type.name

                    proposal["level_id"] = (
                        keep_level.pk
                        if keep_level
                        else None
                    )
                    proposal["level_name"] = (
                        keep_level.name
                        if keep_level
                        else ""
                    )
                    proposal["level_number"] = (
                        keep_level.number
                        if keep_level
                        else None
                    )

                    if not proposal.get(
                        "is_historical"
                    ):
                        proposal["name"] = (
                            f"{keep_type.name} - {keep_level.name}"
                            if keep_level
                            else keep_type.name
                        )

                    errors = _remove_resolution_error(
                        errors,
                        "split",
                    )
                    errors = _remove_resolution_error(
                        errors,
                        "class_type",
                    )

            elif split_action == "split":
                split_specs = []

                split_indexes = sorted(
                    {
                        int(match.group(1))
                        for key in split_data.keys()
                        for match in [
                            re.match(
                                r"^item_(\d+)_class_type_id$",
                                str(key),
                            )
                        ]
                        if match
                    }
                )

                if len(split_indexes) < 2:
                    errors = _remove_resolution_error(
                        errors,
                        "split",
                    )
                    errors.append(
                        "A split resolution needs at least two class splits."
                    )

                for index in split_indexes:
                    prefix = f"item_{index}_"

                    type_id = str(
                        split_data.get(
                            prefix
                            + "class_type_id",
                        )
                        or ""
                    ).strip()

                    level_id = str(
                        split_data.get(
                            prefix
                            + "level_id",
                        )
                        or ""
                    ).strip()

                    type_obj = None
                    level_obj = None

                    if type_id.isdigit():
                        type_obj = (
                            ClassType.objects
                            .filter(
                                studio=studio,
                                pk=int(type_id),
                                is_active=True,
                            )
                            .first()
                        )

                    if type_obj is None:
                        errors.append(
                            f"Split class {index} needs a valid class type."
                        )

                    if level_id == "none":
                        level_obj = None
                    elif level_id.isdigit():
                        level_obj = (
                            ClassLevel.objects
                            .filter(
                                studio=studio,
                                pk=int(level_id),
                                is_active=True,
                            )
                            .first()
                        )
                        if level_obj is None:
                            errors.append(
                                f"Split class {index} needs a valid level."
                            )
                    else:
                        errors.append(
                            f"Split class {index} needs a level "
                            "or an explicit No level selection."
                        )

                    start_text = str(
                        split_data.get(
                            prefix
                            + "start",
                        )
                        or ""
                    ).strip()

                    end_text = str(
                        split_data.get(
                            prefix
                            + "end",
                        )
                        or ""
                    ).strip()

                    duration_minutes = None
                    if not start_text or not end_text:
                        errors.append(
                            f"Split class {index} needs both a start and end time."
                        )
                    else:
                        try:
                            start_value = datetime.strptime(
                                start_text,
                                "%H:%M",
                            )
                            end_value = datetime.strptime(
                                end_text,
                                "%H:%M",
                            )
                            duration_minutes = int(
                                (
                                    end_value
                                    - start_value
                                ).total_seconds()
                                / 60
                            )
                            if duration_minutes <= 0:
                                raise ValueError
                        except ValueError:
                            errors.append(
                                f"Split class {index} needs a valid "
                                "start/end time with end after start."
                            )

                    if (
                        type_obj is not None
                        and (
                            level_id == "none"
                            or level_obj is not None
                        )
                        and duration_minutes is not None
                    ):
                        if proposal.get(
                            "is_historical"
                        ):
                            name = (
                                f"{type_obj.name} - {level_obj.name}"
                                if level_obj
                                else type_obj.name
                            )
                        else:
                            name = (
                                f"{type_obj.name} - {level_obj.name}"
                                if level_obj
                                else type_obj.name
                            )

                        split_specs.append(
                            {
                                "index": index,
                                "class_type_id": type_obj.pk,
                                "class_type_name": type_obj.name,
                                "level_id": (
                                    level_obj.pk
                                    if level_obj
                                    else None
                                ),
                                "level_name": (
                                    level_obj.name
                                    if level_obj
                                    else ""
                                ),
                                "name": name,
                                "start_time": start_text,
                                "duration_minutes": duration_minutes,
                            }
                        )

                if (
                    len(split_indexes) >= 2
                    and split_specs
                    and len(split_specs) == len(split_indexes)
                    and not any(
                        error.startswith("Split class ")
                        or error.startswith(
                            "A split resolution"
                        )
                        for error in errors
                    )
                ):
                    proposal[
                        "_split_specs"
                    ] = split_specs
                    errors = _remove_resolution_error(
                        errors,
                        "split",
                    )
                    errors = _remove_resolution_error(
                        errors,
                        "class_type",
                    )
            else:
                errors = _remove_resolution_error(
                    errors,
                    "split",
                )
                errors.append(
                    "Choose Split into separate classes "
                    "or Keep as one class."
                )

        proposal["_effective_errors"] = errors
        proposal["_effective_status"] = (
            "error" if errors else ("update" if proposal.get("existing_id") else "create")
        )

    return aux_results


def _save_vendor_issue_report(job, row_results):
    issue_rows = [
        item for item in row_results
        if item.status in {DataImportRowResult.Status.ERROR, DataImportRowResult.Status.FAILED}
    ]
    if not issue_rows:
        return

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Row", "Record", "Issue"])
    for item in issue_rows:
        writer.writerow([item.row_number, item.label, item.reason])

    job.rejected_file.save(
        f"studio-director-{job.import_type}-{job.pk}-issues.csv",
        ContentFile(buffer.getvalue().encode("utf-8-sig")),
        save=False,
    )
    job.save(update_fields=["rejected_file"])


@login_required
def studio_director_discovery_commit(request, studio_slug, step_key):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)
    if request.method != "POST":
        return redirect(
            "studios:studio_director_discovery_review",
            studio_slug=studio.slug,
            step_key=step_key,
        )

    step = studio_director_step(step_key)
    if not step or not step.get("discovery"):
        raise Http404("Unknown Studio Director discovery step.")

    state = request.session.get(SESSION_KEY)
    if (
        not state
        or state.get("vendor") != STUDIO_DIRECTOR_VENDOR
        or state.get("vendor_step") != step_key
    ):
        messages.info(request, "Upload the Studio Director report for this step first.")
        return redirect(
            "studios:studio_director_step_upload",
            studio_slug=studio.slug,
            step_key=step_key,
        )

    staged_path = _staged_path_from_state(state, studio)
    if staged_path is None:
        messages.warning(request, "That staged CSV is no longer available. Upload the file again.")
        return redirect(
            "studios:studio_director_step_upload",
            studio_slug=studio.slug,
            step_key=step_key,
        )

    try:
        parsed = parse_csv_path(staged_path)
    except (UnicodeDecodeError, csv.Error, ValueError, OSError) as exc:
        messages.error(request, f"Encore could not re-read the staged CSV: {exc}")
        return redirect(
            "studios:studio_director_step_upload",
            studio_slug=studio.slug,
            step_key=step_key,
        )

    analysis = _vendor_discovery_analysis(studio, step_key, parsed["rows"], extra_rules=((state.get("class_review_translations") or {}).get("rules") if step_key == "classes_meetings" else None))
    proposals = analysis["proposals"]
    run = _studio_director_run(studio, request.user)
    job = _create_vendor_job(
        studio,
        request.user,
        step_key,
        state.get("filename", "studio-director.csv"),
        len(proposals),
    )

    created_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0
    row_results = []

    try:
        selected_keys = set(json.loads(request.POST.get("selected_json", "[]")))
    except (TypeError, ValueError, json.JSONDecodeError):
        selected_keys = set()
    parent_location_id = request.POST.get("parent_location", "").strip()
    parent_location = None
    if parent_location_id:
        parent_location = StudioLocation.objects.filter(
            studio=studio,
            pk=parent_location_id,
        ).first()

    auxiliary_results = []
    if step_key == "classes_meetings":
        # Create any user-approved seasons/types/instructors before class records.
        # Apply-to-all resolutions are grouped by the original Studio Director value.
        with transaction.atomic():
            auxiliary_results = _prepare_class_meeting_resolutions(
                request,
                studio,
                proposals,
                job,
            )
            name_pattern = state.get("class_name_template") or _CLASS_NAME_DEFAULT
            if not _valid_class_name_template(name_pattern):
                raise ValidationError("Invalid saved class name template; upload again.")
            for proposal in proposals:
                edits = (json.loads(request.POST.get("resolutions_json", "{}") or "{}")
                         .get(str(proposal["class_id"]), {}).get("edit", {}))
                if isinstance(edits, dict) and edits.get("enabled") == "true":
                    edit_name = str(edits.get("name") or "").strip()
                    if not edit_name or len(edit_name) > 255:
                        raise ValidationError("Edited class names must contain 1–255 characters.")
                    for key in ("min_age", "max_age"):
                        raw = str(edits.get(key) or "").strip()
                        if raw:
                            try:
                                age = Decimal(raw)
                            except (InvalidOperation, ValueError):
                                raise ValidationError("Enter valid class ages.")
                            if not 0 <= age <= 99:
                                raise ValidationError("Class ages must be between 0 and 99.")
                            proposal[key] = age
                        else:
                            proposal[key] = None
                    if (proposal["min_age"] is not None and proposal["max_age"] is not None
                            and proposal["min_age"] > proposal["max_age"]):
                        raise ValidationError("Minimum class age cannot exceed maximum age.")
                    type_id = str(edits.get("class_type_id") or "")
                    if type_id:
                        selected_type = ClassType.objects.filter(studio=studio, pk=type_id).first()
                        if selected_type is None: raise ValidationError("Invalid class type selection.")
                        proposal["_resolved_class_type_id"] = selected_type.pk
                        proposal["_resolved_class_type_name"] = selected_type.name
                    level_id = str(edits.get("level_id") or "")
                    if level_id:
                        selected_level = (ClassLevel.objects.filter(studio=studio, pk=level_id, is_active=True).first()
                                          if level_id != "none" else None)
                        if level_id != "none" and selected_level is None:
                            raise ValidationError("Invalid class level selection.")
                        proposal["level_id"] = selected_level.pk if selected_level else None
                        proposal["level_name"] = selected_level.name if selected_level else ""
                        proposal["level_number"] = selected_level.number if selected_level else None
                    raw_capacity = str(edits.get("capacity") or "")
                    if raw_capacity:
                        if not raw_capacity.isdigit() or not 1 <= int(raw_capacity) <= 10000:
                            raise ValidationError("Class capacity must be 1–10000.")
                        proposal["capacity"] = int(raw_capacity)
                    proposal["_manual_name_override"] = edit_name
            for proposal in proposals:
                if proposal.get("_manual_name_override"):
                    proposal["name"] = proposal["_manual_name_override"]
                    continue
                if proposal.get("is_historical"):
                    continue  # Preserve historic names used by earlier registrations.
                if proposal.get("_split_specs"):
                    for spec in proposal["_split_specs"]:
                        spec_level = (ClassLevel.objects.filter(studio=studio, pk=spec.get("level_id")).first()
                                      if spec.get("level_id") else None)
                        spec_type = ClassType.objects.filter(studio=studio, pk=spec.get("class_type_id")).first()
                        spec["name"] = _render_class_name(name_pattern, proposal, class_type=spec_type, level=spec_level)
                else:
                    resolved_type = ClassType.objects.filter(
                        studio=studio, pk=proposal.get("_resolved_class_type_id") or proposal.get("class_type_id")
                    ).first()
                    resolved_level = ClassLevel.objects.filter(studio=studio, pk=proposal.get("level_id")).first() if proposal.get("level_id") else None
                    proposal["name"] = _render_class_name(name_pattern, proposal, class_type=resolved_type, level=resolved_level)

    if step_key == "student_measurements":
        with transaction.atomic():
            for index, proposal in enumerate(proposals, start=2):
                key = str(proposal.get("key") or index)
                label = proposal.get("label") or key
                status = proposal.get("status")
                reason = proposal.get("reason", "")
                obj = None
                was_created = False
                before_data = {}
                after_data = {}

                if status == "error":
                    error_count += 1
                    final_status = DataImportRowResult.Status.ERROR

                elif status == "skip":
                    skipped_count += 1
                    final_status = DataImportRowResult.Status.SKIPPED
                    reason = reason or "This measurement record already exists in Encore."

                elif key not in selected_keys:
                    skipped_count += 1
                    final_status = DataImportRowResult.Status.SKIPPED
                    reason = "Not selected on the Studio Director review screen."

                else:
                    try:
                        student = Student.objects.get(
                            pk=proposal["student_id"],
                            studio=studio,
                        )

                        if proposal.get("existing_id"):
                            obj = StudentMeasurementSet.objects.get(
                                pk=proposal["existing_id"],
                                studio=studio,
                                student=student,
                            )
                            before_data = snapshot_instance(obj)
                        else:
                            obj = StudentMeasurementSet(
                                studio=studio,
                                student=student,
                            )
                            was_created = True

                        for field_name in (
                            "bust",
                            "waist",
                            "hips",
                            "girth",
                            "inseam",
                            "outseam",
                            "height",
                        ):
                            raw_value = str(proposal.get(field_name) or "").strip()
                            setattr(
                                obj,
                                field_name,
                                Decimal(raw_value) if raw_value else None,
                            )

                        obj.clothing_size = proposal.get("clothing_size", "")
                        obj.shoe_size = proposal.get("shoe_size", "")
                        obj.other_size_info = proposal.get("other_size_info", "")

                        measured_at_raw = proposal.get("measured_at") or ""
                        if measured_at_raw:
                            measured_at = datetime.fromisoformat(measured_at_raw)
                            if timezone.is_naive(measured_at):
                                measured_at = timezone.make_aware(
                                    measured_at,
                                    timezone.get_current_timezone(),
                                )
                            obj.measured_at = measured_at
                        else:
                            obj.measured_at = None

                        obj.is_complete = bool(proposal.get("is_complete"))

                        source_notes = proposal.get("costume_size_notes") or []
                        if source_notes:
                            source_note_text = "Studio Director: " + "; ".join(source_notes)
                            existing_notes = (obj.notes or "").strip()
                            if source_note_text not in existing_notes:
                                obj.notes = (
                                    f"{existing_notes}\n{source_note_text}".strip()
                                    if existing_notes
                                    else source_note_text
                                )

                        obj.full_clean()
                        obj.save()
                        after_data = snapshot_instance(obj)

                        if was_created:
                            created_count += 1
                            final_status = DataImportRowResult.Status.CREATED
                        else:
                            updated_count += 1
                            final_status = DataImportRowResult.Status.UPDATED

                    except Exception as exc:
                        error_count += 1
                        final_status = DataImportRowResult.Status.FAILED
                        reason = str(exc)
                        obj = None
                        was_created = False
                        before_data = {}
                        after_data = {}

                row_results.append(
                    DataImportRowResult(
                        job=job,
                        row_number=proposal.get("row_number") or index,
                        status=final_status,
                        label=label,
                        reason=reason,
                        source_data=_jsonable(proposal.get("source_data") or {}),
                        normalized_data=_jsonable(proposal),
                        object_type=obj._meta.label_lower if obj is not None else "",
                        object_id=str(obj.pk) if obj is not None else "",
                        was_created=was_created,
                        before_data=_jsonable(before_data),
                        after_data=_jsonable(after_data),
                    )
                )

            DataImportRowResult.objects.bulk_create(row_results)

        _finish_vendor_job(
            job,
            created_count,
            updated_count,
            skipped_count,
            error_count,
        )
        _record_vendor_step_complete(run, step_key, job)

        _remove_staged_file(state, studio)
        request.session.pop(SESSION_KEY, None)
        request.session.modified = True

        messages.success(
            request,
            f'{step["title"]} finished: {created_count} created, '
            f'{updated_count} updated, {skipped_count} skipped, {error_count} error(s).',
        )
        return redirect("studios:studio_director_onboarding", studio_slug=studio.slug)

    if step_key in {"enrollments", "drop_history"}:
        with transaction.atomic():
            for index, proposal in enumerate(proposals, start=2):
                key = str(proposal.get("key") or index)
                label = proposal.get("label") or key
                status = proposal.get("status")
                reason = proposal.get("reason", "")
                obj = None
                was_created = False
                before_data = {}
                after_data = {}

                if status == "error":
                    error_count += 1
                    final_status = DataImportRowResult.Status.ERROR

                elif key not in selected_keys:
                    skipped_count += 1
                    final_status = DataImportRowResult.Status.SKIPPED
                    reason = "Not selected on the Studio Director review screen."

                else:
                    try:
                        obj = Enrollment.objects.filter(
                            student_id=proposal["student_id"],
                            class_instance_id=proposal["class_id"],
                        ).first()

                        if obj is not None:
                            before_data = snapshot_instance(obj)
                            update_values = {
                                "status": proposal["status_value"],
                                "source": Enrollment.Source.IMPORT,
                            }

                            if step_key == "drop_history":
                                update_values["notes"] = proposal.get("notes", "")
                                if proposal.get("dropped_at"):
                                    update_values["dropped_at"] = datetime.fromisoformat(
                                        proposal["dropped_at"]
                                    )
                                if proposal.get("enrolled_at"):
                                    update_values["enrolled_at"] = datetime.fromisoformat(
                                        proposal["enrolled_at"]
                                    )

                            # QuerySet.update deliberately avoids Enrollment post_save billing.
                            Enrollment.objects.filter(pk=obj.pk).update(**update_values)
                            obj.refresh_from_db()
                            updated_count += 1
                            final_status = DataImportRowResult.Status.UPDATED

                        else:
                            obj = Enrollment(
                                student_id=proposal["student_id"],
                                class_instance_id=proposal["class_id"],
                                status=proposal["status_value"],
                                source=Enrollment.Source.IMPORT,
                                notes=proposal.get("notes", ""),
                            )

                            # bulk_create deliberately avoids post_save billing signals.
                            Enrollment.objects.bulk_create([obj])

                            post_values = {}
                            if step_key == "drop_history":
                                if proposal.get("dropped_at"):
                                    post_values["dropped_at"] = datetime.fromisoformat(
                                        proposal["dropped_at"]
                                    )
                                if proposal.get("enrolled_at"):
                                    post_values["enrolled_at"] = datetime.fromisoformat(
                                        proposal["enrolled_at"]
                                    )
                            if post_values:
                                Enrollment.objects.filter(pk=obj.pk).update(**post_values)
                                obj.refresh_from_db()

                            was_created = True
                            created_count += 1
                            final_status = DataImportRowResult.Status.CREATED

                        after_data = snapshot_instance(obj)

                    except Exception as exc:
                        error_count += 1
                        final_status = DataImportRowResult.Status.FAILED
                        reason = str(exc)
                        obj = None
                        was_created = False
                        before_data = {}
                        after_data = {}

                row_results.append(
                    DataImportRowResult(
                        job=job,
                        row_number=proposal.get("row_number") or index,
                        status=final_status,
                        label=label,
                        reason=reason,
                        source_data=_jsonable(proposal.get("source_data") or {}),
                        normalized_data=_jsonable(proposal),
                        object_type=obj._meta.label_lower if obj is not None else "",
                        object_id=str(obj.pk) if obj is not None else "",
                        was_created=was_created,
                        before_data=_jsonable(before_data),
                        after_data=_jsonable(after_data),
                    )
                )

            DataImportRowResult.objects.bulk_create(row_results)

        _finish_vendor_job(
            job,
            created_count,
            updated_count,
            skipped_count,
            error_count,
        )
        _record_vendor_step_complete(run, step_key, job)

        _remove_staged_file(state, studio)
        request.session.pop(SESSION_KEY, None)
        request.session.modified = True

        messages.success(
            request,
            f'{step["title"]} finished: {created_count} created, '
            f'{updated_count} updated, {skipped_count} skipped, {error_count} error(s). '
            "Imported enrollments did not generate billing charges.",
        )
        return redirect("studios:studio_director_onboarding", studio_slug=studio.slug)

    with transaction.atomic():
        for index, proposal in enumerate(proposals, start=2):
            key = str(proposal.get("key") or proposal.get("identity") or index)
            label = proposal.get("name") or proposal.get("class_id") or key
            status = (
                proposal.get("_effective_status")
                if step_key == "classes_meetings"
                else proposal.get("status")
            )
            effective_errors = (
                proposal.get("_effective_errors", [])
                if step_key == "classes_meetings"
                else proposal.get("errors", [])
            )
            if effective_errors:
                reason = " | ".join(effective_errors)
            elif step_key == "classes_meetings" and proposal.get("status") == "error":
                reason = "Resolved during onboarding review."
            else:
                reason = proposal.get("reason", "")
            obj = None
            was_created = False
            before_data = {}
            after_data = {}

            if status == "skip" and step_key != "class_types":
                skipped_count += 1
                final_status = DataImportRowResult.Status.SKIPPED

            elif status == "error":
                error_count += 1
                final_status = DataImportRowResult.Status.ERROR

            elif key not in selected_keys:
                skipped_count += 1
                final_status = DataImportRowResult.Status.SKIPPED
                reason = "Not selected on the Studio Director review screen."

            else:
                try:
                    if step_key == "locations_rooms":
                        obj = StudioRoom.objects.filter(
                            studio=studio,
                            name__iexact=proposal["name"],
                        ).first()
                        if obj:
                            before_data = snapshot_instance(obj)
                            if parent_location and obj.location_id != parent_location.id:
                                obj.location = parent_location
                                obj.full_clean()
                                obj.save(update_fields=["location", "updated_at"])
                                updated_count += 1
                                final_status = DataImportRowResult.Status.UPDATED
                            else:
                                skipped_count += 1
                                final_status = DataImportRowResult.Status.SKIPPED
                                reason = "Room already exists."
                        else:
                            obj = StudioRoom(
                                studio=studio,
                                location=parent_location,
                                name=proposal["name"],
                                is_active=True,
                            )
                            obj.full_clean()
                            obj.save()
                            was_created = True
                            created_count += 1
                            final_status = DataImportRowResult.Status.CREATED

                    elif step_key == "seasons":
                        posted_name = request.POST.get(f"name_{key}", proposal["name"]).strip()
                        posted_start = request.POST.get(f"start_{key}", proposal["start_date"]).strip()
                        posted_end = request.POST.get(f"end_{key}", proposal["end_date"]).strip()

                        if not posted_start or not posted_end:
                            raise ValidationError("Start date and end date are required.")

                        start_date = datetime.fromisoformat(posted_start).date()
                        end_date = datetime.fromisoformat(posted_end).date()

                        obj = Season.objects.filter(
                            studio=studio,
                            name__iexact=posted_name,
                        ).first()
                        if obj:
                            before_data = snapshot_instance(obj)
                            changed = []
                            if obj.start_date != start_date:
                                obj.start_date = start_date
                                changed.append("start_date")
                            if obj.end_date != end_date:
                                obj.end_date = end_date
                                changed.append("end_date")
                            active = end_date >= timezone.localdate()
                            if obj.is_active != active:
                                obj.is_active = active
                                changed.append("is_active")
                            if changed:
                                obj.full_clean()
                                obj.save()
                                updated_count += 1
                                final_status = DataImportRowResult.Status.UPDATED
                            else:
                                skipped_count += 1
                                final_status = DataImportRowResult.Status.SKIPPED
                        else:
                            obj = Season(
                                studio=studio,
                                name=posted_name,
                                start_date=start_date,
                                end_date=end_date,
                                is_active=end_date >= timezone.localdate(),
                                registration_open=False,
                            )
                            obj.full_clean()
                            obj.save()
                            was_created = True
                            created_count += 1
                            final_status = DataImportRowResult.Status.CREATED

                    elif step_key == "class_types":
                        posted_name = request.POST.get(f"name_{key}", proposal["name"]).strip()
                        active_value = request.POST.get(f"active_{key}", "active")
                        if active_value not in {"active", "inactive"}:
                            raise ValidationError("Choose Active or Inactive for each class type.")
                        desired_active = active_value == "active"
                        if not posted_name:
                            raise ValidationError("Class type name is required.")
                        obj = ClassType.objects.filter(
                            studio=studio,
                            name__iexact=posted_name,
                        ).first()
                        if obj:
                            before_data = snapshot_instance(obj)
                            if obj.is_active != desired_active:
                                obj.is_active = desired_active
                                obj.full_clean()
                                obj.save(update_fields=["is_active"])
                                updated_count += 1
                                final_status = DataImportRowResult.Status.UPDATED
                                reason = "Existing class type activity updated."
                            else:
                                skipped_count += 1
                                final_status = DataImportRowResult.Status.SKIPPED
                                reason = "Class type already exists with this activity status."
                        else:
                            obj = ClassType(
                                studio=studio,
                                name=posted_name,
                                is_active=desired_active,
                            )
                            obj.full_clean()
                            obj.save()
                            was_created = True
                            created_count += 1
                            final_status = DataImportRowResult.Status.CREATED

                    elif step_key == "classes_meetings":
                        season = Season.objects.get(
                            pk=proposal.get("_resolved_season_id")
                            or proposal.get("season_id"),
                            studio=studio,
                        )

                        level = None
                        if proposal.get("level_id"):
                            level = ClassLevel.objects.filter(
                                pk=proposal["level_id"],
                                studio=studio,
                            ).first()

                        instructor = Instructor.objects.get(
                            pk=proposal.get("_resolved_instructor_id")
                            or proposal.get("instructor_id"),
                            studio=studio,
                        )

                        assistant = None
                        if proposal.get("assistant_instructor_id"):
                            assistant = Instructor.objects.filter(
                                pk=proposal["assistant_instructor_id"],
                                studio=studio,
                            ).first()

                        split_specs = proposal.get("_split_specs") or []

                        if split_specs:
                            split_objects = []

                            for split_position, split_spec in enumerate(
                                split_specs,
                                start=1,
                            ):
                                split_class_id = proposal["class_id"]
                                if split_position > 1:
                                    split_class_id = (
                                        proposal["class_id"][:45]
                                        + f"-S{split_position}"
                                    )

                                split_class_type = ClassType.objects.get(
                                    pk=split_spec["class_type_id"],
                                    studio=studio,
                                )

                                split_obj = Class.objects.filter(
                                    studio=studio,
                                    class_id=split_class_id,
                                ).first()

                                split_before = (
                                    snapshot_instance(split_obj)
                                    if split_obj
                                    else {}
                                )

                                split_level = None
                                if split_spec.get("level_id"):
                                    split_level = (
                                        ClassLevel.objects
                                        .filter(
                                            pk=split_spec["level_id"],
                                            studio=studio,
                                            is_active=True,
                                        )
                                        .first()
                                    )

                                defaults = {
                                    "season": season,
                                    "class_type": split_class_type,
                                    "level": split_level,
                                    "name": split_spec["name"],
                                    "instructor": instructor,
                                    "assistant_instructor": assistant,
                                    "capacity": proposal["capacity"],
                                    "min_age": proposal.get("min_age"),
                                    "max_age": proposal.get("max_age"),
                                    "is_performance_class": proposal.get(
                                        "is_performance_class"
                                    ),
                                    "allow_drop_ins": proposal["allow_drop_ins"],
                                    "is_active": proposal["is_active"],
                                    "registration_open": proposal.get(
                                        "registration_open",
                                        False,
                                    ),
                                }

                                if split_obj:
                                    for field_name, field_value in defaults.items():
                                        setattr(
                                            split_obj,
                                            field_name,
                                            field_value,
                                        )
                                    split_obj.full_clean()
                                    split_obj.save()
                                    updated_count += 1
                                else:
                                    split_obj = Class(
                                        studio=studio,
                                        class_id=split_class_id,
                                        **defaults,
                                    )
                                    split_obj.full_clean()
                                    split_obj.save()
                                    created_count += 1

                                # The source combined schedule is replaced by the
                                # reviewed split schedule for the resulting class.
                                split_obj.meeting_times.update(
                                    is_active=False
                                )

                                split_start = datetime.strptime(
                                    split_spec["start_time"],
                                    "%H:%M",
                                ).time()

                                source_days = [
                                    meeting.get("day")
                                    for meeting in (
                                        proposal.get("meetings")
                                        or []
                                    )
                                    if meeting.get("day") is not None
                                ]

                                if not source_days and proposal.get("day") is not None:
                                    source_days = [proposal.get("day")]

                                for meeting_day in source_days:
                                    room = None
                                    room_id = proposal.get("room_id")
                                    if room_id:
                                        room = StudioRoom.objects.filter(
                                            studio=studio,
                                            pk=room_id,
                                        ).first()

                                    ClassMeeting.objects.update_or_create(
                                        class_instance=split_obj,
                                        day_of_week=meeting_day,
                                        start_time=split_start,
                                        defaults={
                                            "duration_minutes": (
                                                split_spec["duration_minutes"]
                                                or 60
                                            ),
                                            "room": room,
                                            "location": (
                                                room.location
                                                if room
                                                and room.location_id
                                                else None
                                            ),
                                            "is_active": True,
                                        },
                                    )

                                split_objects.append(split_obj)

                                if split_position > 1:
                                    row_results.append(
                                        DataImportRowResult(
                                            job=job,
                                            row_number=(
                                                200000
                                                + index * 10
                                                + split_position
                                            ),
                                            status=(
                                                DataImportRowResult.Status.UPDATED
                                                if split_before
                                                else DataImportRowResult.Status.CREATED
                                            ),
                                            label=split_obj.name,
                                            reason=(
                                                "Created from a reviewed multi-style "
                                                "Studio Director class split."
                                            ),
                                            source_data={
                                                "source_rows": proposal.get(
                                                    "duplicate_rows"
                                                )
                                                or [
                                                    proposal.get(
                                                        "source_row_number"
                                                    )
                                                ],
                                                "split_from": proposal["class_id"],
                                            },
                                            normalized_data=_jsonable(split_spec),
                                            object_type=split_obj._meta.label_lower,
                                            object_id=str(split_obj.pk),
                                            was_created=not bool(split_before),
                                            before_data=_jsonable(split_before),
                                            after_data=_jsonable(
                                                snapshot_instance(split_obj)
                                            ),
                                        )
                                    )

                            obj = split_objects[0]
                            was_created = not bool(before_data)
                            final_status = (
                                DataImportRowResult.Status.CREATED
                                if not proposal.get("existing_id")
                                else DataImportRowResult.Status.UPDATED
                            )
                            reason += (
                                f" Split into {len(split_objects)} Encore classes."
                            )
                            after_data = snapshot_instance(obj)

                        else:
                            obj = Class.objects.filter(
                                studio=studio,
                                class_id=proposal["class_id"],
                            ).first()

                            class_type = ClassType.objects.get(
                                pk=proposal.get("_resolved_class_type_id")
                                or proposal.get("class_type_id"),
                                studio=studio,
                            )

                            if obj:
                                before_data = snapshot_instance(obj)
                                obj.name = proposal["name"]
                                obj.season = season
                                obj.class_type = class_type
                                obj.level = level
                                obj.min_age = proposal.get("min_age")
                                obj.max_age = proposal.get("max_age")
                                obj.is_performance_class = proposal.get(
                                    "is_performance_class"
                                )
                                obj.instructor = instructor
                                obj.assistant_instructor = assistant
                                obj.capacity = proposal["capacity"]
                                obj.allow_drop_ins = proposal["allow_drop_ins"]
                                obj.is_active = proposal["is_active"]
                                obj.registration_open = proposal.get(
                                    "registration_open",
                                    False,
                                )
                                obj.full_clean()
                                obj.save()
                                updated_count += 1
                                final_status = DataImportRowResult.Status.UPDATED
                            else:
                                obj = Class(
                                    studio=studio,
                                    season=season,
                                    class_type=class_type,
                                    level=level,
                                    class_id=proposal["class_id"],
                                    name=proposal["name"],
                                    instructor=instructor,
                                    assistant_instructor=assistant,
                                    capacity=proposal["capacity"],
                                    min_age=proposal.get("min_age"),
                                    max_age=proposal.get("max_age"),
                                    is_performance_class=proposal.get(
                                        "is_performance_class"
                                    ),
                                    allow_drop_ins=proposal["allow_drop_ins"],
                                    is_active=proposal["is_active"],
                                    registration_open=proposal.get(
                                        "registration_open",
                                        False,
                                    ),
                                )
                                obj.full_clean()
                                obj.save()
                                was_created = True
                                created_count += 1
                                final_status = DataImportRowResult.Status.CREATED

                            meeting_payloads = proposal.get("meetings") or []
                            if (
                                not meeting_payloads
                                and proposal.get("day") is not None
                                and proposal.get("start_time")
                            ):
                                meeting_payloads = [
                                    {
                                        "day": proposal.get("day"),
                                        "start_time": proposal.get("start_time"),
                                        "duration_minutes": proposal.get(
                                            "duration_minutes",
                                            60,
                                        ),
                                        "room_id": proposal.get("room_id"),
                                    }
                                ]

                            meeting_created_count = 0
                            meeting_updated_count = 0
                            for meeting_payload in meeting_payloads:
                                room = None
                                if meeting_payload.get("room_id"):
                                    room = StudioRoom.objects.filter(
                                        studio=studio,
                                        pk=meeting_payload["room_id"],
                                    ).first()

                                if (
                                    meeting_payload.get("day") is None
                                    or not meeting_payload.get("start_time")
                                ):
                                    continue

                                meeting_start_time = datetime.strptime(
                                    meeting_payload["start_time"],
                                    "%H:%M",
                                ).time()

                                _meeting, meeting_created = (
                                    ClassMeeting.objects.update_or_create(
                                        class_instance=obj,
                                        day_of_week=meeting_payload["day"],
                                        start_time=meeting_start_time,
                                        defaults={
                                            "duration_minutes": (
                                                meeting_payload.get(
                                                    "duration_minutes"
                                                )
                                                or proposal.get(
                                                    "duration_minutes",
                                                    60,
                                                )
                                            ),
                                            "room": room,
                                            "location": (
                                                room.location
                                                if room
                                                and room.location_id
                                                else None
                                            ),
                                            "is_active": True,
                                        },
                                    )
                                )

                                if meeting_created:
                                    meeting_created_count += 1
                                else:
                                    meeting_updated_count += 1

                            if meeting_created_count:
                                reason += (
                                    f" {meeting_created_count} meeting(s) created."
                                )

                            if meeting_updated_count:
                                reason += (
                                    f" {meeting_updated_count} meeting(s) synchronized."
                                )

                    else:
                        raise ValidationError("Unsupported Studio Director discovery step.")

                    if obj is not None:
                        after_data = snapshot_instance(obj)

                except Exception as exc:
                    error_count += 1
                    final_status = DataImportRowResult.Status.FAILED
                    reason = str(exc)
                    obj = None
                    was_created = False
                    before_data = {}
                    after_data = {}

            row_results.append(
                DataImportRowResult(
                    job=job,
                    row_number=index,
                    status=final_status,
                    label=label,
                    reason=reason,
                    source_data={
                        "source_rows": proposal.get("source_rows")
                        or proposal.get("duplicate_rows")
                        or [proposal.get("source_row_number")],
                        "warnings": proposal.get("warnings", []),
                    },
                    normalized_data=_jsonable(proposal),
                    object_type=obj._meta.label_lower if obj is not None else "",
                    object_id=str(obj.pk) if obj is not None else "",
                    was_created=was_created,
                    before_data=_jsonable(before_data),
                    after_data=_jsonable(after_data),
                )
            )

        if auxiliary_results:
            row_results.extend(auxiliary_results)
        DataImportRowResult.objects.bulk_create(row_results)

    _finish_vendor_job(
        job,
        created_count,
        updated_count,
        skipped_count,
        error_count,
    )
    if step_key == "classes_meetings":
        _save_vendor_issue_report(job, row_results)
    _record_vendor_step_complete(run, step_key, job)
    if step_key == "classes_meetings":
        completed_state = dict(run.step_state or {})
        completed_state["class_name_pattern"] = state.get("class_name_template") or _CLASS_NAME_DEFAULT
        run.step_state = completed_state
        run.save(update_fields=["step_state", "updated_at"])

    _remove_staged_file(state, studio)
    request.session.pop(SESSION_KEY, None)
    request.session.modified = True

    messages.success(
        request,
        f'{step["title"]} finished: {created_count} created, '
        f'{updated_count} updated, {skipped_count} skipped, {error_count} error(s).',
    )
    return redirect("studios:studio_director_onboarding", studio_slug=studio.slug)


BILLING_SUMMARY_HEADERS = {
    "Guardian First Name",
    "Guardian Last Name",
    "Email",
    "Total Unpaid Charges",
    "Payments Not Applied to Unpaid Charges",
    "Balance Due",
}

BILLING_DETAIL_HEADERS = {
    "Guardian First Name",
    "Guardian Last Name",
    "Email",
    "Charge Category",
    "0-30",
    "31-60",
    "61-90",
    "Over 90",
    "Unpaid Charges",
}


def _billing_decimal(value):
    text = str(value or "").strip().replace("$", "").replace(",", "")
    if not text:
        return Decimal("0.00")
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValidationError(f'"{value}" is not a valid dollar amount.')


def _read_billing_csv(path, required_headers):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = [str(item or "").strip() for item in (reader.fieldnames or [])]
        missing = [name for name in required_headers if name not in headers]
        if missing:
            raise ValidationError(
                "Missing required CSV column(s): " + ", ".join(sorted(missing))
            )
        return [
            {str(key or "").strip(): str(value or "").strip() for key, value in row.items()}
            for row in reader
            if any(str(value or "").strip() for value in row.values())
        ]


def _billing_family_key(row):
    email = str(row.get("Email") or "").strip().lower()
    if email:
        return f"email:{email}"
    first = str(row.get("Guardian First Name") or "").strip().lower()
    last = str(row.get("Guardian Last Name") or "").strip().lower()
    return f"name:{first}|{last}"


def _match_billing_family(studio, row):
    email = str(row.get("Email") or "").strip()
    first = str(row.get("Guardian First Name") or "").strip()
    last = str(row.get("Guardian Last Name") or "").strip()

    matches = []

    if email:
        family_qs = Family.objects.filter(studio=studio).filter(
            Q(primary_email__iexact=email)
            | Q(secondary_email__iexact=email)
            | Q(guardians__email__iexact=email)
        ).distinct()
        matches = list(family_qs[:3])

    if not matches and first and last:
        family_qs = Family.objects.filter(studio=studio).filter(
            Q(
                primary_contact_first_name__iexact=first,
                primary_contact_last_name__iexact=last,
            )
            | Q(
                primary_contact_first_name__iexact=first,
                family_name__iexact=last,
            )
        ).distinct()
        matches = list(family_qs[:3])

    if len(matches) == 1:
        return matches[0], ""
    if len(matches) > 1:
        return None, (
            f'Multiple Encore families match {first} {last} / {email}. '
            "Resolve the duplicate family records before importing balances."
        )
    return None, f'No Encore family matches {first} {last} / {email}.'


def _billing_charge_type(category):
    value = str(category or "").strip().lower()
    if value == "tuition":
        return Charge.ChargeType.TUITION
    if value in {"registration", "registration fee"}:
        return Charge.ChargeType.REGISTRATION
    if value in {"late fee", "late fees"}:
        return Charge.ChargeType.LATE_FEE
    if value in {"costume", "costume balance", "costume fee"}:
        return Charge.ChargeType.COSTUME
    if value in {"performance", "performance fee"}:
        return Charge.ChargeType.PERFORMANCE
    if value in {"merchandise", "merch"}:
        return Charge.ChargeType.MERCHANDISE
    return Charge.ChargeType.OTHER


def _analyze_billing_transition(studio, summary_rows, detail_rows):
    detail_by_family = {}
    for row in detail_rows:
        key = _billing_family_key(row)
        detail_by_family.setdefault(key, []).append(row)

    families = []
    source_unpaid = Decimal("0.00")
    source_unapplied = Decimal("0.00")
    source_balance = Decimal("0.00")
    detail_unpaid = Decimal("0.00")
    errors = []

    for row in summary_rows:
        family_key = _billing_family_key(row)
        matched_family, match_error = _match_billing_family(studio, row)

        total_unpaid = _billing_decimal(row.get("Total Unpaid Charges"))
        unapplied = _billing_decimal(row.get("Payments Not Applied to Unpaid Charges"))
        balance_due = _billing_decimal(row.get("Balance Due"))
        source_unpaid += total_unpaid
        source_unapplied += unapplied
        source_balance += balance_due

        family_details = detail_by_family.get(family_key, [])
        family_detail_total = sum(
            (_billing_decimal(item.get("Unpaid Charges")) for item in family_details),
            Decimal("0.00"),
        )
        detail_unpaid += family_detail_total

        family_errors = []
        if match_error:
            family_errors.append(match_error)
        if not family_details:
            family_errors.append("No Family Charge Detail rows matched this summary row.")
        if family_detail_total != total_unpaid:
            family_errors.append(
                f"Detail charges total ${family_detail_total:.2f}, "
                f"but Family Balance Summary says ${total_unpaid:.2f}."
            )
        expected_balance = (total_unpaid + unapplied).quantize(Decimal("0.01"))
        if expected_balance != balance_due:
            family_errors.append(
                f"Unpaid charges plus unapplied payments equals ${expected_balance:.2f}, "
                f"but Balance Due is ${balance_due:.2f}."
            )

        families.append(
            {
                "key": family_key,
                "family": matched_family,
                "family_id": matched_family.pk if matched_family else None,
                "guardian_first_name": row.get("Guardian First Name", ""),
                "guardian_last_name": row.get("Guardian Last Name", ""),
                "email": row.get("Email", ""),
                "total_unpaid": total_unpaid,
                "unapplied": unapplied,
                "balance_due": balance_due,
                "details": [
                    {
                        **item,
                        "amount": _billing_decimal(item.get("Unpaid Charges")),
                        "age_0_30": _billing_decimal(item.get("0-30")),
                        "age_31_60": _billing_decimal(item.get("31-60")),
                        "age_61_90": _billing_decimal(item.get("61-90")),
                        "age_over_90": _billing_decimal(item.get("Over 90")),
                    }
                    for item in family_details
                ],
                "errors": family_errors,
            }
        )
        errors.extend(family_errors)

    summary_keys = {_billing_family_key(row) for row in summary_rows}
    orphan_detail_keys = sorted(set(detail_by_family) - summary_keys)
    for key in orphan_detail_keys:
        errors.append(f"Charge Detail contains a family not present in Family Balance Summary: {key}")

    overall_expected_balance = (source_unpaid + source_unapplied).quantize(Decimal("0.01"))
    reconciliation = {
        "summary_unpaid": source_unpaid,
        "detail_unpaid": detail_unpaid,
        "unapplied": source_unapplied,
        "summary_balance": source_balance,
        "calculated_balance": overall_expected_balance,
        "unpaid_difference": (source_unpaid - detail_unpaid).quantize(Decimal("0.01")),
        "balance_difference": (source_balance - overall_expected_balance).quantize(Decimal("0.01")),
    }

    if reconciliation["unpaid_difference"] != Decimal("0.00"):
        errors.append(
            "Overall Family Charge Detail does not reconcile to Family Balance Summary."
        )
    if reconciliation["balance_difference"] != Decimal("0.00"):
        errors.append(
            "Overall Balance Due does not reconcile to unpaid charges plus unapplied payments."
        )

    ready_families = [item for item in families if not item["errors"]]
    issue_families = [item for item in families if item["errors"]]

    ready_unpaid = sum(
        (item["total_unpaid"] for item in ready_families),
        Decimal("0.00"),
    )
    ready_unapplied = sum(
        (item["unapplied"] for item in ready_families),
        Decimal("0.00"),
    )
    ready_balance = sum(
        (item["balance_due"] for item in ready_families),
        Decimal("0.00"),
    )

    return {
        "families": families,
        "ready_families": ready_families,
        "issue_families": issue_families,
        "errors": errors,
        "reconciliation": reconciliation,
        "matched_count": sum(1 for item in families if item["family_id"]),
        "ready_count": len(ready_families),
        "issue_count": len(issue_families),
        "family_count": len(families),
        "detail_count": len(detail_rows),
        "ready_unpaid": ready_unpaid,
        "ready_unapplied": ready_unapplied,
        "ready_balance": ready_balance,
    }


def _billing_transition_state(request, studio):
    state = request.session.get(BILLING_TRANSITION_SESSION_KEY) or {}
    if state.get("studio_id") != studio.pk:
        return {}
    return state


def _remove_billing_staged_files(state):
    for key in ("summary_path", "detail_path"):
        value = (state or {}).get(key)
        if not value:
            continue
        try:
            Path(value).unlink(missing_ok=True)
        except OSError:
            pass


@login_required
def studio_director_billing_transition(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    run = _studio_director_run(studio, request.user)
    current = (run.step_state or {}).get("billing_transition") or {}
    current_job = None
    if current.get("job_id"):
        current_job = DataImportJob.objects.filter(
            studio=studio,
            pk=current["job_id"],
        ).first()

    if request.method == "POST":
        summary_file = request.FILES.get("summary_csv")
        detail_file = request.FILES.get("detail_csv")
        opening_balance_date = request.POST.get("opening_balance_date", "").strip()
        billing_start_date = request.POST.get("billing_start_date", "").strip()

        if not summary_file or not detail_file:
            messages.error(request, "Choose both billing CSV files.")
        elif not summary_file.name.lower().endswith(".csv") or not detail_file.name.lower().endswith(".csv"):
            messages.error(request, "Both billing files must be CSV files.")
        elif not opening_balance_date or not billing_start_date:
            messages.error(request, "Opening balance date and Encore billing start date are required.")
        else:
            try:
                datetime.fromisoformat(opening_balance_date).date()
                datetime.fromisoformat(billing_start_date).date()
            except ValueError:
                messages.error(request, "Enter valid dates.")
            else:
                old_state = _billing_transition_state(request, studio)
                _remove_billing_staged_files(old_state)

                staging = _staging_root(studio)
                summary_path = staging / f"{uuid.uuid4().hex}-family-balance-summary.csv"
                detail_path = staging / f"{uuid.uuid4().hex}-family-charge-detail.csv"

                with summary_path.open("wb") as handle:
                    for chunk in summary_file.chunks():
                        handle.write(chunk)
                with detail_path.open("wb") as handle:
                    for chunk in detail_file.chunks():
                        handle.write(chunk)

                try:
                    summary_rows = _read_billing_csv(summary_path, BILLING_SUMMARY_HEADERS)
                    detail_rows = _read_billing_csv(detail_path, BILLING_DETAIL_HEADERS)
                    _analyze_billing_transition(studio, summary_rows, detail_rows)
                except (UnicodeDecodeError, csv.Error, ValidationError, OSError) as exc:
                    summary_path.unlink(missing_ok=True)
                    detail_path.unlink(missing_ok=True)
                    messages.error(request, f"Encore could not read the billing CSVs: {exc}")
                else:
                    request.session[BILLING_TRANSITION_SESSION_KEY] = {
                        "studio_id": studio.pk,
                        "summary_filename": summary_file.name,
                        "detail_filename": detail_file.name,
                        "summary_path": str(summary_path),
                        "detail_path": str(detail_path),
                        "opening_balance_date": opening_balance_date,
                        "billing_start_date": billing_start_date,
                    }
                    request.session.modified = True
                    return redirect(
                        "studios:studio_director_billing_transition_review",
                        studio_slug=studio.slug,
                    )

    return render(
        request,
        "studios/studio_director_billing_transition.html",
        {
            "studio": studio,
            "role": "administrator",
            "settings_section": "data_transfer",
            "current_job": current_job,
            "current": current,
        },
    )


@login_required
def studio_director_billing_transition_review(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    state = _billing_transition_state(request, studio)
    if not state:
        messages.info(request, "Upload both Studio Director billing CSVs first.")
        return redirect(
            "studios:studio_director_billing_transition",
            studio_slug=studio.slug,
        )

    try:
        summary_rows = _read_billing_csv(state["summary_path"], BILLING_SUMMARY_HEADERS)
        detail_rows = _read_billing_csv(state["detail_path"], BILLING_DETAIL_HEADERS)
        analysis = _analyze_billing_transition(studio, summary_rows, detail_rows)
    except (UnicodeDecodeError, csv.Error, ValidationError, OSError, FileNotFoundError) as exc:
        messages.error(request, f"Encore could not re-read the staged billing files: {exc}")
        return redirect(
            "studios:studio_director_billing_transition",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "studios/studio_director_billing_transition_review.html",
        {
            "studio": studio,
            "role": "administrator",
            "settings_section": "data_transfer",
            "state": state,
            "analysis": analysis,
        },
    )


@login_required
def studio_director_billing_transition_issues_csv(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    state = _billing_transition_state(request, studio)
    if not state:
        raise Http404("No staged Billing Transition files are available.")

    try:
        summary_rows = _read_billing_csv(state["summary_path"], BILLING_SUMMARY_HEADERS)
        detail_rows = _read_billing_csv(state["detail_path"], BILLING_DETAIL_HEADERS)
        analysis = _analyze_billing_transition(studio, summary_rows, detail_rows)
    except (UnicodeDecodeError, csv.Error, ValidationError, OSError, FileNotFoundError) as exc:
        raise Http404(f"Encore could not read the staged billing files: {exc}")

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="{studio.slug}-billing-transition-issues.csv"'
    )
    writer = csv.writer(response)
    writer.writerow([
        "Guardian First Name",
        "Guardian Last Name",
        "Email",
        "Total Unpaid Charges",
        "Payments Not Applied to Unpaid Charges",
        "Balance Due",
        "Issue",
    ])

    for item in analysis["issue_families"]:
        for issue in item["errors"]:
            writer.writerow([
                item["guardian_first_name"],
                item["guardian_last_name"],
                item["email"],
                f'{item["total_unpaid"]:.2f}',
                f'{item["unapplied"]:.2f}',
                f'{item["balance_due"]:.2f}',
                issue,
            ])

    family_issue_text = {
        issue
        for item in analysis["issue_families"]
        for issue in item["errors"]
    }
    for issue in analysis["errors"]:
        if issue in family_issue_text:
            continue
        writer.writerow(["", "", "", "", "", "", issue])

    return response


@login_required
def studio_director_billing_transition_commit(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)
    if request.method != "POST":
        return redirect(
            "studios:studio_director_billing_transition_review",
            studio_slug=studio.slug,
        )

    state = _billing_transition_state(request, studio)
    if not state:
        messages.info(request, "Upload both Studio Director billing CSVs first.")
        return redirect(
            "studios:studio_director_billing_transition",
            studio_slug=studio.slug,
        )

    run = _studio_director_run(studio, request.user)
    existing_state = (run.step_state or {}).get("billing_transition") or {}
    if existing_state.get("status") == "completed" and existing_state.get("job_id"):
        existing_job = DataImportJob.objects.filter(
            studio=studio,
            pk=existing_state["job_id"],
        ).first()
        if existing_job and existing_job.status != DataImportJob.Status.REVERTED:
            messages.error(
                request,
                "Billing Transition has already been imported. Undo the current billing-transition import before importing it again.",
            )
            return redirect(
                "studios:studio_director_billing_transition",
                studio_slug=studio.slug,
            )

    try:
        summary_rows = _read_billing_csv(state["summary_path"], BILLING_SUMMARY_HEADERS)
        detail_rows = _read_billing_csv(state["detail_path"], BILLING_DETAIL_HEADERS)
        analysis = _analyze_billing_transition(studio, summary_rows, detail_rows)
    except (UnicodeDecodeError, csv.Error, ValidationError, OSError, FileNotFoundError) as exc:
        messages.error(request, f"Encore could not read the staged billing files: {exc}")
        return redirect(
            "studios:studio_director_billing_transition",
            studio_slug=studio.slug,
        )

    if not analysis["ready_families"]:
        messages.error(
            request,
            "No billing families are currently safe to import. Review the issues report and correct at least one family before continuing.",
        )
        return redirect(
            "studios:studio_director_billing_transition_review",
            studio_slug=studio.slug,
        )

    opening_date = datetime.fromisoformat(state["opening_balance_date"]).date()
    billing_start_date = datetime.fromisoformat(state["billing_start_date"]).date()

    job = DataImportJob.objects.create(
        studio=studio,
        created_by=request.user,
        import_type="studio_director_billing_transition",
        original_filename=f'{state["summary_filename"]} + {state["detail_filename"]}',
        total_rows=analysis["family_count"],
    )

    row_results = []
    created_count = 0
    row_number = 2

    try:
        with transaction.atomic():
            # Import only families that passed matching and reconciliation.
            # Families with issues are recorded below as ERROR rows and do not
            # block the ready families.
            for family_item in analysis["ready_families"]:
                family = Family.objects.get(
                    studio=studio,
                    pk=family_item["family_id"],
                )
                account, _ = FamilyAccount.objects.get_or_create(
                    studio=studio,
                    family=family,
                    defaults={"is_active": True},
                )

                for detail in family_item["details"]:
                    amount = detail["amount"]
                    if amount <= 0:
                        continue

                    category = detail.get("Charge Category", "").strip() or "Other"
                    charge = Charge(
                        account=account,
                        charge_type=_billing_charge_type(category),
                        description=f"Studio Director opening balance - {category}",
                        amount=amount,
                        status=Charge.Status.OPEN,
                        notes=(
                            f"Imported from Studio Director Aging / Collections. "
                            f"Opening balance date: {opening_date.isoformat()}. "
                            f"Aging: 0-30 ${detail['age_0_30']:.2f}; "
                            f"31-60 ${detail['age_31_60']:.2f}; "
                            f"61-90 ${detail['age_61_90']:.2f}; "
                            f"Over 90 ${detail['age_over_90']:.2f}."
                        ),
                    )
                    charge.full_clean()
                    charge.save()
                    created_count += 1

                    row_results.append(
                        DataImportRowResult(
                            job=job,
                            row_number=row_number,
                            status=DataImportRowResult.Status.CREATED,
                            label=f"{family.family_name} - {category}",
                            reason="Opening Studio Director charge imported.",
                            source_data=_jsonable(detail),
                            normalized_data={
                                "family_id": family.pk,
                                "category": category,
                                "amount": str(amount),
                                "opening_balance_date": opening_date.isoformat(),
                            },
                            object_type=charge._meta.label_lower,
                            object_id=str(charge.pk),
                            was_created=True,
                            before_data={},
                            after_data=_jsonable(snapshot_instance(charge)),
                        )
                    )
                    row_number += 1

                if family_item["unapplied"] < 0:
                    amount = abs(family_item["unapplied"])
                    credit = Credit(
                        account=account,
                        credit_type=Credit.CreditType.MANUAL,
                        description="Studio Director opening unapplied payment",
                        amount=amount,
                        notes=(
                            "Imported from Studio Director Aging / Collections "
                            f"as of {opening_date.isoformat()}. Left unapplied so "
                            "the family opening balance reconciles to Studio Director."
                        ),
                    )
                    credit.full_clean()
                    credit.save()
                    created_count += 1

                    row_results.append(
                        DataImportRowResult(
                            job=job,
                            row_number=row_number,
                            status=DataImportRowResult.Status.CREATED,
                            label=f"{family.family_name} - opening credit",
                            reason="Unapplied Studio Director payment imported as an Encore account credit.",
                            source_data={
                                "Payments Not Applied to Unpaid Charges": str(family_item["unapplied"]),
                            },
                            normalized_data={
                                "family_id": family.pk,
                                "amount": str(amount),
                                "opening_balance_date": opening_date.isoformat(),
                            },
                            object_type=credit._meta.label_lower,
                            object_id=str(credit.pk),
                            was_created=True,
                            before_data={},
                            after_data=_jsonable(snapshot_instance(credit)),
                        )
                    )
                    row_number += 1

            for family_item in analysis["issue_families"]:
                row_results.append(
                    DataImportRowResult(
                        job=job,
                        row_number=row_number,
                        status=DataImportRowResult.Status.ERROR,
                        label=(
                            f'{family_item["guardian_first_name"]} '
                            f'{family_item["guardian_last_name"]}'
                        ).strip(),
                        reason=" | ".join(family_item["errors"]),
                        source_data={
                            "Guardian First Name": family_item["guardian_first_name"],
                            "Guardian Last Name": family_item["guardian_last_name"],
                            "Email": family_item["email"],
                            "Total Unpaid Charges": str(family_item["total_unpaid"]),
                            "Payments Not Applied to Unpaid Charges": str(family_item["unapplied"]),
                            "Balance Due": str(family_item["balance_due"]),
                        },
                        normalized_data={},
                        before_data={},
                        after_data={},
                    )
                )
                row_number += 1

            DataImportRowResult.objects.bulk_create(row_results)

        job.created_count = created_count
        job.updated_count = 0
        job.skipped_count = 0
        job.error_count = analysis["issue_count"]
        job.failed_count = 0
        job.status = (
            DataImportJob.Status.COMPLETED_WITH_ISSUES
            if analysis["issue_count"] or analysis["errors"]
            else DataImportJob.Status.COMPLETED
        )
        job.completed_at = timezone.now()

        if analysis["issue_count"] or analysis["errors"]:
            issue_buffer = io.StringIO()
            issue_writer = csv.writer(issue_buffer)
            issue_writer.writerow([
                "Guardian First Name",
                "Guardian Last Name",
                "Email",
                "Total Unpaid Charges",
                "Payments Not Applied to Unpaid Charges",
                "Balance Due",
                "Issue",
            ])
            for item in analysis["issue_families"]:
                for issue in item["errors"]:
                    issue_writer.writerow([
                        item["guardian_first_name"],
                        item["guardian_last_name"],
                        item["email"],
                        f'{item["total_unpaid"]:.2f}',
                        f'{item["unapplied"]:.2f}',
                        f'{item["balance_due"]:.2f}',
                        issue,
                    ])

            family_issue_text = {
                issue
                for item in analysis["issue_families"]
                for issue in item["errors"]
            }
            for issue in analysis["errors"]:
                if issue in family_issue_text:
                    continue
                issue_writer.writerow(["", "", "", "", "", "", issue])

            job.rejected_file.save(
                f"{studio.slug}-billing-transition-{job.pk}-issues.csv",
                ContentFile(issue_buffer.getvalue().encode("utf-8-sig")),
                save=False,
            )

        job.save()

    except Exception as exc:
        job.status = DataImportJob.Status.FAILED
        job.failure_message = str(exc)
        job.error_count = 1
        job.completed_at = timezone.now()
        job.save()
        messages.error(request, f"Billing Transition failed and was rolled back: {exc}")
        return redirect(
            "studios:studio_director_billing_transition_review",
            studio_slug=studio.slug,
        )

    run_state = dict(run.step_state or {})
    run_state["billing_transition"] = {
        "status": "completed",
        "job_id": job.pk,
        "filename": job.original_filename,
        "created": job.created_count,
        "updated": 0,
        "not_imported": analysis["issue_count"],
        "completed_at": timezone.now().isoformat(),
        "opening_balance_date": opening_date.isoformat(),
        "billing_start_date": billing_start_date.isoformat(),
        "source_unpaid": str(analysis["reconciliation"]["summary_unpaid"]),
        "source_unapplied": str(analysis["reconciliation"]["unapplied"]),
        "source_balance": str(analysis["reconciliation"]["summary_balance"]),
        "imported_unpaid": str(analysis["ready_unpaid"]),
        "imported_unapplied": str(analysis["ready_unapplied"]),
        "imported_balance": str(analysis["ready_balance"]),
    }
    run.step_state = run_state
    run.save(update_fields=["step_state", "updated_at"])

    _remove_billing_staged_files(state)
    request.session.pop(BILLING_TRANSITION_SESSION_KEY, None)
    request.session.modified = True

    if analysis["issue_count"]:
        messages.warning(
            request,
            "Billing Transition imported the ready families and skipped "
            f'{analysis["issue_count"]} famil{"y" if analysis["issue_count"] == 1 else "ies"} '
            "that need review. The issues CSV is saved with the import in Import History. "
            f'Imported net opening balance: ${analysis["ready_balance"]:.2f}. '
            f'Encore billing start date: {billing_start_date:%b %d, %Y}.',
        )
    else:
        messages.success(
            request,
            "Billing Transition imported successfully. "
            f'Opening receivables ${analysis["ready_unpaid"]:.2f}, '
            f'unapplied credits ${abs(analysis["ready_unapplied"]):.2f}, '
            f'net balance ${analysis["ready_balance"]:.2f}. '
            f'Encore billing start date recorded as {billing_start_date:%b %d, %Y}.',
        )
    return redirect("studios:studio_director_onboarding", studio_slug=studio.slug)


@login_required
def studio_director_final_review(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    run = _studio_director_run(studio, request.user)

    step_state = run.step_state or {}
    billing_transition = step_state.get("billing_transition") or {}

    # Final Review should represent the CURRENT onboarding state, not every
    # historical test/re-run. Each completed playbook step stores its latest job_id.
    current_job_ids = []
    for step_key, step_result in step_state.items():
        job_id = (step_result or {}).get("job_id")
        if job_id:
            current_job_ids.append(job_id)

    current_jobs_qs = DataImportJob.objects.filter(
        studio=studio,
        pk__in=current_job_ids,
    ).order_by("-created_at")

    recent_jobs = list(current_jobs_qs)

    unresolved_rows = DataImportRowResult.objects.filter(
        job_id__in=current_job_ids,
        status__in=[
            DataImportRowResult.Status.ERROR,
            DataImportRowResult.Status.FAILED,
        ],
    ).count()

    unresolved_jobs = DataImportJob.objects.filter(
        pk__in=current_job_ids,
    ).filter(
        row_results__status__in=[
            DataImportRowResult.Status.ERROR,
            DataImportRowResult.Status.FAILED,
        ]
    ).distinct().count()

    tbd_instructors = Instructor.objects.filter(
        studio=studio,
        first_name__iexact="TBD",
        last_name__iexact="Instructor",
        is_active=True,
    ).count()

    current_enrollments = Enrollment.objects.filter(
        class_instance__studio=studio,
        status=Enrollment.Status.ACTIVE,
    ).count()

    waitlisted = Enrollment.objects.filter(
        class_instance__studio=studio,
        status=Enrollment.Status.WAITLISTED,
    ).count()

    dropped = Enrollment.objects.filter(
        class_instance__studio=studio,
        status=Enrollment.Status.DROPPED,
    ).count()

    measurement_records = StudentMeasurementSet.objects.filter(
        studio=studio,
    ).count()

    students_with_measurements = Student.objects.filter(
        studio=studio,
        measurement_sets__isnull=False,
    ).distinct().count()

    return render(
        request,
        "studios/studio_director_final_review.html",
        {
            "studio": studio,
            "role": "administrator",
            "settings_section": "data_transfer",
            "run": run,
            "billing_transition": billing_transition,
            "recent_jobs": recent_jobs,
            "unresolved_rows": unresolved_rows,
            "unresolved_jobs": unresolved_jobs,
            "tbd_instructors": tbd_instructors,
            "current_enrollments": current_enrollments,
            "waitlisted": waitlisted,
            "dropped": dropped,
            "measurement_records": measurement_records,
            "students_with_measurements": students_with_measurements,
        },
    )


@login_required
def studio_director_mark_manual_step(request, studio_slug, step_key):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)
    if request.method != "POST":
        return redirect("studios:studio_director_onboarding", studio_slug=studio.slug)

    step = studio_director_step(step_key)
    if not step or not step.get("manual"):
        raise Http404("This step cannot be marked manually.")

    run = _studio_director_run(studio, request.user)
    state = dict(run.step_state or {})
    existing_step_state = dict(
        state.get(step_key) or {}
    )
    existing_step_state.update(
        {
            "status": "completed",
            "completed_at": timezone.now().isoformat(),
            "manual": True,
        }
    )
    state[step_key] = existing_step_state
    run.step_state = state
    run.save(update_fields=["step_state", "updated_at"])
    messages.success(request, f'{step["title"]} marked complete.')
    return redirect("studios:studio_director_onboarding", studio_slug=studio.slug)


@login_required
def data_import_upload(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    if request.method == "POST":
        import_type = request.POST.get("import_type", "").strip()
        uploaded_file = request.FILES.get("csv_file")

        if import_type not in IMPORT_TYPES:
            messages.error(request, "Choose what kind of data this file contains.")
        elif uploaded_file is None:
            messages.error(request, "Choose a CSV file to upload.")
        elif not uploaded_file.name.lower().endswith(".csv"):
            messages.error(request, "Encore currently accepts CSV files for imports.")
        elif uploaded_file.size > 10 * 1024 * 1024:
            messages.error(request, "CSV files must be 10 MB or smaller for this import step.")
        else:
            try:
                parsed = parse_csv_upload(uploaded_file)
            except UnicodeDecodeError:
                messages.error(request, "Encore could not read that file as UTF-8 CSV data.")
            except (csv.Error, ValueError) as exc:
                messages.error(request, str(exc))
            else:
                old_state = request.session.get(SESSION_KEY)
                _remove_staged_file(old_state, studio)

                staged_path = _staging_root(studio) / f"{uuid.uuid4().hex}.csv"
                staged_path.write_text(parsed["text"], encoding="utf-8-sig")

                request.session[SESSION_KEY] = {
                    "filename": uploaded_file.name,
                    "import_type": import_type,
                    "headers": parsed["headers"],
                    "preview_rows": parsed["preview_rows"],
                    "total_rows": parsed["total_rows"],
                    "mapping": auto_map_headers(parsed["headers"], import_type),
                    "staged_path": str(staged_path),
                }
                request.session.modified = True
                return redirect("studios:data_import_map", studio_slug=studio.slug)

    return render(
        request,
        "studios/data_import_upload.html",
        {
            "studio": studio,
            "role": "administrator",
            "settings_section": "data_transfer",
            "import_types": IMPORT_TYPES,
        },
    )


@login_required
def data_import_map(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    state = request.session.get(SESSION_KEY)
    if not state or state.get("import_type") not in IMPORT_TYPES:
        messages.info(request, "Upload a CSV file before mapping columns.")
        return redirect("studios:data_import_upload", studio_slug=studio.slug)

    if _staged_path_from_state(state, studio) is None:
        messages.warning(request, "That staged CSV is no longer available. Upload the file again.")
        return redirect("studios:data_import_upload", studio_slug=studio.slug)

    import_type = state["import_type"]
    fields = IMPORT_TYPES[import_type]["fields"]

    if request.method == "POST":
        mapping = {}
        seen_fields = set()
        duplicate_fields = set()
        allowed = {field for field, _label in fields}

        for index, header in enumerate(state["headers"]):
            target = request.POST.get(f"column_{index}", "").strip()
            if target not in allowed:
                target = ""
            if target and target in seen_fields:
                duplicate_fields.add(target)
            if target:
                seen_fields.add(target)
            mapping[header] = target

        if duplicate_fields:
            messages.error(
                request,
                "Each Encore field can only be mapped once. Remove the duplicate mappings and try again.",
            )
        else:
            missing = required_mapping_errors(import_type, mapping)
            if state.get("vendor") == STUDIO_DIRECTOR_VENDOR and state.get("vendor_step") == "guardians":
                missing = [
                    error for error in missing
                    if "Family primary email" not in error
                ]
            if missing:
                for error in missing:
                    messages.error(request, error)
            else:
                state["mapping"] = mapping
                request.session[SESSION_KEY] = state
                request.session.modified = True
                return redirect("studios:data_import_review", studio_slug=studio.slug)

    mapped_headers = []
    labels = dict(fields)
    mapping = state.get("mapping") or {}
    for index, header in enumerate(state["headers"]):
        selected = mapping.get(header, "")
        mapped_headers.append(
            {
                "index": index,
                "header": header,
                "selected": selected,
                "selected_label": labels.get(selected, "Ignore this column"),
            }
        )

    return render(
        request,
        "studios/data_import_map.html",
        {
            "studio": studio,
            "role": "administrator",
            "settings_section": "data_transfer",
            "state": state,
            "import_type": IMPORT_TYPES[import_type],
            "fields": fields,
            "mapped_headers": mapped_headers,
        },
    )


@login_required
def data_import_review(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    state = request.session.get(SESSION_KEY)
    if not state or state.get("import_type") not in IMPORT_TYPES:
        messages.info(request, "Upload and map a CSV file before reviewing it.")
        return redirect("studios:data_import_upload", studio_slug=studio.slug)

    mapping_errors = required_mapping_errors(state["import_type"], state.get("mapping") or {})
    if state.get("vendor") == STUDIO_DIRECTOR_VENDOR and state.get("vendor_step") == "guardians":
        mapping_errors = [
            error for error in mapping_errors
            if "Family primary email" not in error
        ]
    if mapping_errors:
        for error in mapping_errors:
            messages.error(request, error)
        return redirect("studios:data_import_map", studio_slug=studio.slug)

    staged_path = _staged_path_from_state(state, studio)
    if staged_path is None:
        messages.warning(request, "That staged CSV is no longer available. Upload the file again.")
        return redirect("studios:data_import_upload", studio_slug=studio.slug)

    try:
        parsed = parse_csv_path(staged_path)
    except (UnicodeDecodeError, csv.Error, ValueError, OSError) as exc:
        messages.error(request, f"Encore could not re-read the staged CSV: {exc}")
        return redirect("studios:data_import_upload", studio_slug=studio.slug)

    analysis = analyze_import_rows(
        studio,
        state["import_type"],
        parsed["rows"],
        state["mapping"],
        vendor=state.get("vendor"),
        vendor_step=state.get("vendor_step"),
    )

    status_filter = request.GET.get("status", "all").strip().lower()
    allowed_filters = {"all", "create", "update", "skip", "error"}
    if status_filter not in allowed_filters:
        status_filter = "all"

    visible_results = analysis["results"]
    if status_filter != "all":
        visible_results = [row for row in visible_results if row["status"] == status_filter]

    return render(
        request,
        "studios/data_import_review.html",
        {
            "studio": studio,
            "role": "administrator",
            "settings_section": "data_transfer",
            "state": state,
            "import_type": IMPORT_TYPES[state["import_type"]],
            "counts": analysis["counts"],
            "results": visible_results,
            "status_filter": status_filter,
        },
    )



def _jsonable(value):
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "as_tuple"):
        return str(value)
    return value


def _rejected_csv_content(headers, row_results):
    buffer = io.StringIO()
    report_headers = list(headers) + [
        "Encore Import Result",
        "Encore Reason",
        "Encore Details",
    ]
    writer = csv.DictWriter(buffer, fieldnames=report_headers, extrasaction="ignore")
    writer.writeheader()

    for result in row_results:
        if result["final_status"] not in {"skipped", "error", "failed"}:
            continue
        source = dict(result.get("source_row") or {})
        source["Encore Import Result"] = result["final_status"].title()
        source["Encore Reason"] = result.get("reason", "")
        source["Encore Details"] = " | ".join(result.get("errors") or [])
        writer.writerow(source)

    return buffer.getvalue().encode("utf-8-sig")


@login_required
def data_import_commit(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)
    if request.method != "POST":
        return redirect("studios:data_import_review", studio_slug=studio.slug)

    state = request.session.get(SESSION_KEY)
    if not state or state.get("import_type") not in IMPORT_TYPES:
        messages.info(request, "Upload and map a CSV file before importing it.")
        return redirect("studios:data_import_upload", studio_slug=studio.slug)

    staged_path = _staged_path_from_state(state, studio)
    if staged_path is None:
        messages.warning(request, "That staged CSV is no longer available. Upload the file again.")
        return redirect("studios:data_import_upload", studio_slug=studio.slug)

    try:
        parsed = parse_csv_path(staged_path)
    except (UnicodeDecodeError, csv.Error, ValueError, OSError) as exc:
        messages.error(request, f"Encore could not re-read the staged CSV: {exc}")
        return redirect("studios:data_import_upload", studio_slug=studio.slug)

    analysis = analyze_import_rows(
        studio,
        state["import_type"],
        parsed["rows"],
        state["mapping"],
        vendor=state.get("vendor"),
        vendor_step=state.get("vendor_step"),
    )

    job = DataImportJob.objects.create(
        studio=studio,
        created_by=request.user,
        import_type=state["import_type"],
        original_filename=state.get("filename", "import.csv"),
        total_rows=analysis["counts"]["total"],
    )

    committed_rows = []
    created_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0
    failed_count = 0

    try:
        with transaction.atomic():
            for result in analysis["results"]:
                final_status = result["status"]
                reason = result.get("reason", "")
                errors = list(result.get("errors") or [])
                obj = None
                was_created = False
                before_data = {}
                after_data = {}

                if final_status == "skip":
                    skipped_count += 1
                    final_status = "skipped"
                elif final_status == "error":
                    error_count += 1
                    final_status = "error"
                else:
                    try:
                        with transaction.atomic():
                            obj, was_created, before_data = commit_import_result(
                                studio,
                                state["import_type"],
                                result,
                            )
                            if (
                                state.get("vendor") == STUDIO_DIRECTOR_VENDOR
                                and state.get("vendor_step") == "instructors"
                                and isinstance(obj, Instructor)
                                and not obj.claimed_at
                            ):
                                obj.is_active = False
                                obj.save(
                                    update_fields=[
                                        "is_active",
                                        "updated_at",
                                    ]
                                )
                    except (ValidationError, IntegrityError) as exc:
                        failed_count += 1
                        final_status = "failed"
                        reason = str(exc)
                        errors = [str(exc)]
                    else:
                        after_data = snapshot_instance(obj)
                        if was_created:
                            created_count += 1
                            final_status = "created"
                            reason = "Record created successfully."
                        else:
                            updated_count += 1
                            final_status = "updated"
                            reason = "Existing record updated successfully."

                committed_rows.append(
                    {
                        **result,
                        "final_status": final_status,
                        "reason": reason,
                        "errors": errors,
                        "object": obj,
                        "was_created": was_created,
                        "before_data": before_data,
                        "after_data": after_data,
                    }
                )

            DataImportRowResult.objects.bulk_create(
                [
                    DataImportRowResult(
                        job=job,
                        row_number=item["row_number"],
                        status=item["final_status"],
                        label=item.get("label", ""),
                        reason=item.get("reason", ""),
                        source_data=_jsonable(item.get("source_row") or {}),
                        normalized_data=_jsonable(item.get("normalized") or {}),
                        object_type=(
                            item["object"]._meta.label_lower
                            if item.get("object") is not None
                            else ""
                        ),
                        object_id=(
                            str(item["object"].pk)
                            if item.get("object") is not None and item["object"].pk is not None
                            else ""
                        ),
                        was_created=bool(item.get("was_created")),
                        before_data=_jsonable(item.get("before_data") or {}),
                        after_data=_jsonable(item.get("after_data") or {}),
                    )
                    for item in committed_rows
                ]
            )
    except Exception as exc:
        job.status = DataImportJob.Status.FAILED
        job.failure_message = str(exc)
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "failure_message", "completed_at"])
        messages.error(
            request,
            "Encore stopped the import because of an unexpected system error. No import changes were committed.",
        )
        return redirect("studios:data_import_result", studio_slug=studio.slug, job_id=job.pk)

    job.created_count = created_count
    job.updated_count = updated_count
    job.skipped_count = skipped_count
    job.error_count = error_count
    job.failed_count = failed_count
    job.completed_at = timezone.now()
    job.status = (
        DataImportJob.Status.COMPLETED_WITH_ISSUES
        if skipped_count or error_count or failed_count
        else DataImportJob.Status.COMPLETED
    )

    rejected_content = _rejected_csv_content(state["headers"], committed_rows)
    if skipped_count or error_count or failed_count:
        report_name = f"{studio.slug}-import-{job.pk}-not-imported.csv"
        job.rejected_file.save(report_name, ContentFile(rejected_content), save=False)

    job.save()

    if state.get("vendor") == STUDIO_DIRECTOR_VENDOR and state.get("vendor_step"):
        run = VendorOnboardingRun.objects.filter(
            pk=state.get("vendor_run_id"),
            studio=studio,
            vendor=STUDIO_DIRECTOR_VENDOR,
        ).first()
        if run:
            run_state = dict(run.step_state or {})
            run_state[state["vendor_step"]] = {
                "status": "completed",
                "job_id": job.pk,
                "filename": job.original_filename,
                "created": job.created_count,
                "updated": job.updated_count,
                "not_imported": job.not_imported_count,
                "completed_at": timezone.now().isoformat(),
            }
            run.step_state = run_state
            run.save(update_fields=["step_state", "updated_at"])

    _remove_staged_file(state, studio)
    request.session.pop(SESSION_KEY, None)
    request.session.modified = True

    messages.success(
        request,
        f"Import finished: {created_count} created, {updated_count} updated, "
        f"{skipped_count + error_count + failed_count} not imported.",
    )
    return redirect("studios:data_import_result", studio_slug=studio.slug, job_id=job.pk)


@login_required
def data_import_result(request, studio_slug, job_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    job = get_object_or_404(
        DataImportJob.objects.select_related("created_by"),
        pk=job_id,
        studio=studio,
    )
    row_results = job.row_results.all()
    return render(
        request,
        "studios/data_import_result.html",
        {
            "studio": studio,
            "role": "administrator",
            "settings_section": "data_transfer",
            "job": job,
            "row_results": row_results,
            "import_type": IMPORT_TYPES.get(job.import_type, {"label": job.import_type.title()}),
        },
    )


@login_required
def data_import_rejected_csv(request, studio_slug, job_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    job = get_object_or_404(DataImportJob, pk=job_id, studio=studio)
    if not job.rejected_file:
        raise Http404("This import does not have a rejected-row CSV.")

    try:
        job.rejected_file.open("rb")
        content = job.rejected_file.read()
    finally:
        job.rejected_file.close()

    response = HttpResponse(content, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="{studio.slug}-import-{job.pk}-not-imported.csv"'
    )
    return response


@login_required
def data_import_history(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    jobs = (
        DataImportJob.objects
        .filter(studio=studio)
        .select_related("created_by", "reverted_by")
        .prefetch_related("row_results")
    )

    return render(
        request,
        "studios/data_import_history.html",
        {
            "studio": studio,
            "role": "administrator",
            "settings_section": "data_transfer",
            "jobs": jobs,
        },
    )


@login_required
def data_import_history_detail(request, studio_slug, job_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    job = get_object_or_404(
        DataImportJob.objects.select_related("created_by", "reverted_by"),
        pk=job_id,
        studio=studio,
    )

    return render(
        request,
        "studios/data_import_history_detail.html",
        {
            "studio": studio,
            "role": "administrator",
            "settings_section": "data_transfer",
            "job": job,
            "row_results": job.row_results.all(),
            "import_type": IMPORT_TYPES.get(
                job.import_type,
                {"label": job.import_type.title()},
            ),
        },
    )


@login_required
def data_import_undo(request, studio_slug, job_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    if request.method != "POST":
        return redirect(
            "studios:data_import_history_detail",
            studio_slug=studio.slug,
            job_id=job_id,
        )

    with transaction.atomic():
        job = get_object_or_404(
            DataImportJob.objects.select_for_update(),
            pk=job_id,
            studio=studio,
        )

        if job.status == DataImportJob.Status.REVERTED:
            messages.info(request, "This import has already been undone.")
            return redirect(
                "studios:data_import_history_detail",
                studio_slug=studio.slug,
                job_id=job.pk,
            )

        reverted_count = 0
        blocked_count = 0

        rows = (
            job.row_results
            .select_for_update()
            .filter(
                status__in=[
                    DataImportRowResult.Status.CREATED,
                    DataImportRowResult.Status.UPDATED,
                ]
            )
            .order_by("-id")
        )

        for row in rows:
            obj = resolve_import_object(row)

            if row.status == DataImportRowResult.Status.CREATED:
                if obj is None:
                    row.status = DataImportRowResult.Status.REVERT_BLOCKED
                    row.revert_message = "The created record no longer exists."
                    row.save(update_fields=["status", "revert_message"])
                    blocked_count += 1
                    continue

                if row.after_data and not snapshot_matches(obj, row.after_data):
                    row.status = DataImportRowResult.Status.REVERT_BLOCKED
                    row.revert_message = (
                        "This record changed after the import, so Encore left it alone."
                    )
                    row.save(update_fields=["status", "revert_message"])
                    blocked_count += 1
                    continue

                deleted, message = safe_delete_created_record(obj)

                if not deleted:
                    row.status = DataImportRowResult.Status.REVERT_BLOCKED
                    row.revert_message = message
                    row.save(update_fields=["status", "revert_message"])
                    blocked_count += 1
                    continue

                row.status = DataImportRowResult.Status.REVERTED
                row.revert_message = message
                row.save(update_fields=["status", "revert_message"])
                reverted_count += 1
                continue

            if obj is None:
                row.status = DataImportRowResult.Status.REVERT_BLOCKED
                row.revert_message = "The updated record no longer exists."
                row.save(update_fields=["status", "revert_message"])
                blocked_count += 1
                continue

            if row.after_data and not snapshot_matches(obj, row.after_data):
                row.status = DataImportRowResult.Status.REVERT_BLOCKED
                row.revert_message = (
                    "This record changed after the import, so Encore did not overwrite newer changes."
                )
                row.save(update_fields=["status", "revert_message"])
                blocked_count += 1
                continue

            try:
                restore_snapshot(obj, row.before_data)
            except (ValidationError, IntegrityError, ValueError) as exc:
                row.status = DataImportRowResult.Status.REVERT_BLOCKED
                row.revert_message = f"Encore could not restore the previous values safely: {exc}"
                row.save(update_fields=["status", "revert_message"])
                blocked_count += 1
                continue

            row.status = DataImportRowResult.Status.REVERTED
            row.revert_message = "Previous values restored."
            row.save(update_fields=["status", "revert_message"])
            reverted_count += 1

        job.reverted_at = timezone.now()
        job.reverted_by = request.user

        if blocked_count:
            job.status = DataImportJob.Status.COMPLETED_WITH_ISSUES
        else:
            job.status = DataImportJob.Status.REVERTED

        job.save(
            update_fields=[
                "status",
                "reverted_at",
                "reverted_by",
            ]
        )

    if blocked_count:
        messages.warning(
            request,
            f"Undo finished: {reverted_count} row(s) reversed and "
            f"{blocked_count} row(s) left unchanged for safety.",
        )
    else:
        messages.success(
            request,
            f"Import #{job.pk} was undone. {reverted_count} row(s) were reversed.",
        )

    return redirect(
        "studios:data_import_history_detail",
        studio_slug=studio.slug,
        job_id=job.pk,
    )



def _write_csv_to_zip(archive, filename, headers, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([csv_value(value) for value in row])
    archive.writestr(filename, buffer.getvalue().encode("utf-8-sig"))


@login_required
def data_export(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    export_choices = [
        ("students", "Students"),
        ("families", "Families"),
        ("guardians", "Guardians"),
        ("instructors", "Teachers / Instructors"),
        ("classes", "Classes"),
        ("enrollments", "Enrollments"),
    ]

    if request.method != "POST":
        return render(
            request,
            "studios/data_export.html",
            {
                "studio": studio,
                "role": "administrator",
                "settings_section": "data_transfer",
                "export_choices": export_choices,
            },
        )

    selected = request.POST.getlist("datasets")
    allowed = {key for key, _label in export_choices}
    selected = [key for key in selected if key in allowed]

    if not selected:
        messages.error(request, "Choose at least one data set to export.")
        return redirect("studios:data_export", studio_slug=studio.slug)

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        if "families" in selected:
            headers = [
                "family_id", "family_name", "primary_contact_first_name", "primary_contact_last_name",
                "primary_email", "secondary_email", "primary_phone", "secondary_phone",
                "address_line_1", "address_line_2", "city", "state", "postal_code",
                "emergency_contact_name", "emergency_contact_phone", "emergency_contact_relationship",
                "how_did_you_hear_about_us", "notes", "is_active",
            ]
            rows = (
                Family.objects.filter(studio=studio)
                .order_by("id")
                .values_list(
                    "id", "family_name", "primary_contact_first_name", "primary_contact_last_name",
                    "primary_email", "secondary_email", "primary_phone", "secondary_phone",
                    "address_line_1", "address_line_2", "city", "state", "postal_code",
                    "emergency_contact_name", "emergency_contact_phone", "emergency_contact_relationship",
                    "how_did_you_hear_about_us", "notes", "is_active",
                )
            )
            _write_csv_to_zip(archive, "families.csv", headers, rows)

        if "guardians" in selected:
            headers = [
                "guardian_id", "family_id", "first_name", "last_name", "relationship", "email", "phone",
                "is_primary", "is_authorized_for_pickup", "is_financially_responsible", "is_active",
            ]
            rows = (
                Guardian.objects.filter(family__studio=studio)
                .order_by("id")
                .values_list(
                    "id", "family_id", "first_name", "last_name", "relationship", "email", "phone",
                    "is_primary", "is_authorized_for_pickup", "is_financially_responsible", "is_active",
                )
            )
            _write_csv_to_zip(archive, "guardians.csv", headers, rows)

        if "students" in selected:
            headers = [
                "student_id", "family_id", "first_name", "last_name", "birthday", "gender",
                "medical_conditions", "allergies", "comments", "paper_waiver_on_file", "performing",
                "is_active", "enrollment_blocked", "emergency_contact_name", "emergency_contact_phone",
                "emergency_contact_relationship", "how_did_you_hear_about_us",
            ]
            rows = (
                Student.objects.filter(studio=studio)
                .order_by("id")
                .values_list(
                    "id", "family_id", "first_name", "last_name", "birthday", "gender",
                    "medical_conditions", "allergies", "comments", "paper_waiver_on_file", "performing",
                    "is_active", "enrollment_blocked", "emergency_contact_name", "emergency_contact_phone",
                    "emergency_contact_relationship", "how_did_you_hear_about_us",
                )
            )
            _write_csv_to_zip(archive, "students.csv", headers, rows)

        if "instructors" in selected:
            headers = [
                "instructor_id", "first_name", "last_name", "email", "phone", "address_line_1",
                "address_line_2", "city", "state", "postal_code", "emergency_contact_name",
                "emergency_contact_phone", "emergency_contact_relationship", "bio", "is_active",
            ]
            rows = (
                Instructor.objects.filter(studio=studio)
                .order_by("id")
                .values_list(
                    "id", "first_name", "last_name", "email", "phone", "address_line_1", "address_line_2",
                    "city", "state", "postal_code", "emergency_contact_name", "emergency_contact_phone",
                    "emergency_contact_relationship", "bio", "is_active",
                )
            )
            _write_csv_to_zip(archive, "instructors.csv", headers, rows)

        if "classes" in selected:
            headers = [
                "class_id", "name", "season", "class_type", "instructor_email", "assistant_instructor_email",
                "capacity", "min_age", "max_age", "gender_restriction", "tuition_amount", "allow_drop_ins",
                "drop_in_price", "is_active", "registration_open", "description", "dress_code", "notes",
            ]
            rows = []
            for item in (
                Class.objects.filter(studio=studio)
                .select_related("season", "class_type", "instructor", "assistant_instructor")
                .order_by("class_id")
            ):
                rows.append([
                    item.class_id,
                    item.name,
                    item.season.name,
                    item.class_type.name,
                    item.instructor.email,
                    item.assistant_instructor.email if item.assistant_instructor else "",
                    item.capacity,
                    item.min_age,
                    item.max_age,
                    item.gender_restriction,
                    item.tuition_amount,
                    item.allow_drop_ins,
                    item.drop_in_price,
                    item.is_active,
                    item.registration_open,
                    item.description,
                    item.dress_code,
                    item.notes,
                ])
            _write_csv_to_zip(archive, "classes.csv", headers, rows)

        if "enrollments" in selected:
            headers = [
                "enrollment_id", "student_id", "student_first_name", "student_last_name", "student_birthday",
                "class_id", "class_name", "status", "source", "tuition_override", "enrolled_at",
                "dropped_at", "waitlisted_at", "notes",
            ]
            rows = []
            for enrollment in (
                Enrollment.objects.filter(student__studio=studio)
                .select_related("student", "class_instance")
                .order_by("id")
            ):
                rows.append([
                    enrollment.id,
                    enrollment.student_id,
                    enrollment.student.first_name,
                    enrollment.student.last_name,
                    enrollment.student.birthday,
                    enrollment.class_instance.class_id,
                    enrollment.class_instance.name,
                    enrollment.status,
                    enrollment.source,
                    enrollment.tuition_override,
                    enrollment.enrolled_at,
                    enrollment.dropped_at,
                    enrollment.waitlisted_at,
                    enrollment.notes,
                ])
            _write_csv_to_zip(archive, "enrollments.csv", headers, rows)

        readme = {
            "studio": studio.name,
            "format": "Encore Performance Suite portable CSV export",
            "relationships": {
                "students.family_id": "families.family_id",
                "guardians.family_id": "families.family_id",
                "enrollments.student_id": "students.student_id",
                "enrollments.class_id": "classes.class_id",
            },
            "included": selected,
        }
        archive.writestr("README.json", json.dumps(readme, indent=2))

    output.seek(0)
    response = HttpResponse(output.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = (
        f'attachment; filename="{studio.slug}-encore-export.zip"'
    )
    return response


@login_required
def studio_director_billing_activation(request, studio_slug):
    from datetime import date
    from django.core.paginator import Paginator
    from .import_billing_activation import activation_preview, activate_imported_billing, save_family_adjustment

    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)
    run = _studio_director_run(studio, request.user)
    state = run.step_state or {}
    transition = state.get('billing_transition') or {}
    today = timezone.localdate()
    recorded = transition.get('billing_start_date')
    try:
        minimum = max(today, date.fromisoformat(recorded)) if recorded else today
    except (ValueError, TypeError):
        minimum = today
    chosen = request.POST.get('cutover') if request.method == 'POST' else request.GET.get('cutover')
    try:
        cutover = date.fromisoformat(chosen) if chosen else minimum
    except (ValueError, TypeError):
        cutover = minimum
    if cutover < minimum:
        if request.method == 'POST':
            messages.error(request, 'Activation cannot precede today or the approved billing transition date.')
        cutover = minimum
    if request.method == 'POST':
        action = request.POST.get('action', 'activate')
        if action == 'adjust':
            try:
                family_id = int(request.POST.get('family_id', ''))
                season_id = int(request.POST.get('season_id', ''))
                # Only allow editing a family/season currently under imported billing review.
                _, current_rows = activation_preview(studio, cutover)
                if not any(r['kind'] == 'family' and r['family'].pk == family_id and r['season'].pk == season_id for r in current_rows):
                    raise ValueError('This family/season is not part of the current imported billing review.')
                if any(r['kind'] == 'family' and r['family'].pk == family_id and r['season'].pk == season_id and r['status'] == 'existing' for r in current_rows):
                    raise ValueError('An existing schedule cannot be adjusted in import activation.')
                save_family_adjustment(studio, family_id, season_id, request.POST.get('amount', ''))
                messages.success(request, 'Tuition adjustment saved. Preview recalculated; no schedules or charges created.')
            except (ValueError, TypeError) as exc:
                messages.error(request, str(exc))
            return redirect(f"{reverse('studios:studio_director_billing_activation', kwargs={'studio_slug': studio.slug})}?cutover={cutover.isoformat()}&q={request.POST.get('q', '')[:60]}")
        if (transition.get('status') != 'completed'
                or (state.get('final_review') or {}).get('status') != 'completed'):
            messages.error(request, 'Complete Billing Transition and Final Review before activation.')
        elif request.POST.get('confirm') != 'ACTIVATE':
            messages.error(request, 'Type ACTIVATE to confirm the billing cutover.')
        elif chosen != cutover.isoformat():
            messages.error(request, 'Select a valid future activation date.')
        else:
            try:
                created, counts = activate_imported_billing(studio, cutover)
            except ValueError as exc:
                messages.error(request, str(exc))
            else:
                new_state = dict(run.step_state or {})
                new_state['billing_activation'] = {
                    'status': 'completed', 'cutover': cutover.isoformat(),
                    'created': created, 'completed_at': timezone.now().isoformat(),
                    'completed_by': request.user.pk,
                }
                run.step_state = new_state
                run.save(update_fields=['step_state', 'updated_at'])
                messages.success(request, f'{created} recurring tuition schedules activated. '
                                         'Unresolved items remain available for review. No charges were generated.')
                return redirect('studios:studio_director_billing_activation', studio_slug=studio.slug)
    counts, all_rows = activation_preview(studio, cutover)
    query = request.GET.get('q', '').strip()[:60]
    status_filter = request.GET.get('status', '')
    rows = all_rows
    if status_filter in ('eligible', 'existing', 'missing'):
        rows = [r for r in rows if r['status'] == status_filter]
    if query:
        term = query.lower()
        rows = [r for r in rows if term in (f"{r['family'].family_name} {r['class_names']} {r['season']}" if r['kind'] == 'family' else f"{r['enrollment'].student} {r['enrollment'].class_instance.name}").lower()]
    page = Paginator(rows, 25).get_page(request.GET.get('page'))
    return render(request, 'studios/studio_director_billing_activation.html', {
        'studio': studio, 'role': 'administrator', 'settings_section': 'data_transfer',
        'counts': counts, 'rows': page.object_list, 'page_obj': page,
        'filtered_count': len(rows), 'q': query, 'status_filter': status_filter,
        'cutover': cutover, 'minimum': minimum,
        'transition_complete': transition.get('status') == 'completed',
        'final_complete': (state.get('final_review') or {}).get('status') == 'completed',
        'activation_state': (state.get('billing_activation') or {}),
    })


@login_required
def studio_director_special_class_tuition(request, studio_slug):
    """Optional bulk editor; changes only requested fields on selected classes."""
    from billing.models import StudioTuitionSettings, TuitionPlan
    from django.core.paginator import Paginator
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)
    run = _studio_director_run(studio, request.user)
    settings_obj = StudioTuitionSettings.objects.filter(studio=studio).first()
    plans = TuitionPlan.objects.filter(studio=studio).order_by('name')
    query = (request.GET.get('q') or request.POST.get('q') or '').strip()[:80]
    season_filter = request.GET.get('season') or request.POST.get('season') or ''
    pricing_filter = request.GET.get('pricing') or request.POST.get('pricing') or ''
    type_filter = request.GET.get('type') or request.POST.get('type') or ''
    level_filter = request.GET.get('level') or request.POST.get('level') or ''
    age_min = request.GET.get('age_min') or request.POST.get('age_min') or ''
    age_max = request.GET.get('age_max') or request.POST.get('age_max') or ''
    classes = Class.objects.filter(studio=studio).select_related('season', 'tuition_plan', 'class_type', 'level').order_by('season__name', 'name', 'pk')
    if query:
        classes = classes.filter(Q(name__icontains=query) | Q(season__name__icontains=query) | Q(class_type__name__icontains=query) | Q(level__name__icontains=query))
    if season_filter.isdigit():
        classes = classes.filter(season_id=int(season_filter))
    if type_filter.isdigit():
        classes = classes.filter(class_type_id=int(type_filter))
    if level_filter.isdigit():
        classes = classes.filter(level_id=int(level_filter))
    # Include open-ended class age ranges when checking overlap.
    try:
        if age_min.strip():
            min_value = Decimal(age_min)
            if min_value < 0 or min_value > 120: raise ValueError()
            classes = classes.filter(Q(max_age__gte=min_value) | Q(max_age__isnull=True))
        if age_max.strip():
            max_value = Decimal(age_max)
            if max_value < 0 or max_value > 120: raise ValueError()
            classes = classes.filter(Q(min_age__lte=max_value) | Q(min_age__isnull=True))
        if age_min.strip() and age_max.strip() and Decimal(age_min) > Decimal(age_max): raise ValueError()
    except (ValueError, InvalidOperation):
        messages.error(request, 'Enter a valid age range from 0 to 120.')
        return redirect('studios:studio_director_special_class_tuition', studio_slug=studio.slug)
    if pricing_filter == 'special':
        classes = classes.filter(tuition_amount__isnull=False)
    elif pricing_filter == 'standard':
        classes = classes.filter(tuition_amount__isnull=True)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'skip':
            messages.error(request, 'Use Skip on the Studio Director Playbook.')
            return redirect('studios:studio_director_onboarding', studio_slug=studio.slug)
        if action == 'complete':
            state = dict(run.step_state or {})
            state['special_class_tuition'] = {'status': 'completed', 'completed_at': timezone.now().isoformat(), 'completed_by': request.user.pk}
            run.step_state = state
            run.save(update_fields=['step_state', 'updated_at'])
            messages.success(request, 'Special Class Tuition review completed.')
            return redirect('studios:studio_director_onboarding', studio_slug=studio.slug)
        if action == 'bulk_save':
            selection = request.POST.get('selection', 'selected')
            if selection == 'filtered':
                ids = list(classes.values_list('pk', flat=True))
            else:
                ids = []
                for value in request.POST.getlist('class_ids'):
                    if value.isdigit():
                        ids.append(int(value))
                ids = list(classes.filter(pk__in=ids).values_list('pk', flat=True))
            # Explicit field-level toggles prevent clearing other class data.
            change_pricing = request.POST.get('change_pricing') == 'on'
            change_policy = request.POST.get('change_policy') == 'on'
            updates = {}
            try:
                if not ids:
                    raise ValueError('Select at least one class using the table checkboxes.')
                if len(ids) > 10000:
                    raise ValueError('Please narrow the filter to 10,000 classes or fewer.')
                if not change_pricing and not change_policy:
                    raise ValueError('Choose at least one field to update.')
                if change_pricing:
                    mode = request.POST.get('pricing_mode')
                    if mode == 'studio':
                        updates['tuition_amount'] = None
                    elif mode == 'custom':
                        raw = request.POST.get('tuition_amount', '').strip()
                        try:
                            amount = Decimal(raw)
                        except (InvalidOperation, ValueError):
                            raise ValueError('Enter a valid custom tuition amount.')
                        if not amount.is_finite() or amount < 0 or amount >= Decimal('100000000') or amount.as_tuple().exponent < -2:
                            raise ValueError('Custom tuition must be a nonnegative amount with at most two decimals.')
                        updates['tuition_amount'] = amount
                    else:
                        raise ValueError('Choose studio-wide or custom tuition pricing.')
                if change_policy:
                    policy_id = request.POST.get('tuition_plan_id', '')
                    if policy_id == 'clear':
                        updates['tuition_plan'] = None
                    elif policy_id.isdigit():
                        updates['tuition_plan'] = plans.filter(pk=int(policy_id)).first()
                        if updates['tuition_plan'] is None:
                            raise ValueError('Choose a policy from this studio.')
                    else:
                        raise ValueError('Choose a billing policy or Clear.')
                with transaction.atomic():
                    updated = Class.objects.filter(studio=studio, pk__in=ids).update(**updates)
                messages.success(request, f'Updated {updated} classes. Existing billed amounts and schedules were not modified.')
            except ValueError as exc:
                messages.error(request, str(exc))
            return redirect(f"{reverse('studios:studio_director_special_class_tuition', kwargs={'studio_slug': studio.slug})}?{__import__('urllib.parse', fromlist=['urlencode']).urlencode({'q':query, 'season':season_filter, 'pricing':pricing_filter, 'type':type_filter, 'level':level_filter, 'age_min':age_min, 'age_max':age_max})}")
    all_seasons = Season.objects.filter(studio=studio).order_by('-start_date')
    page = Paginator(classes, 40).get_page(request.GET.get('page'))
    return render(request, 'studios/studio_director_special_class_tuition.html', {
        'studio':studio, 'classes':page.object_list, 'page_obj':page,
        'total_matching':classes.count(), 'q':query, 'season_filter':season_filter,
        'pricing_filter':pricing_filter, 'type_filter':type_filter, 'level_filter':level_filter, 'age_min':age_min, 'age_max':age_max,
        'types':ClassType.objects.filter(studio=studio).order_by('name'), 'levels':ClassLevel.objects.filter(studio=studio).order_by('name'), 'seasons':all_seasons, 'plans':plans,
        'studio_wide':bool(settings_obj and settings_obj.is_studio_wide),
        'step_state':(run.step_state or {}).get('special_class_tuition') or {},
    })
