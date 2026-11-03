
import csv
import io

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from studios.models import Studio, DataImportJob, DataImportRowResult
from .data_transfer_history_services import (
    get_imported_object,
    restore_snapshot,
    snapshot_matches,
)


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


def _deny(request, studio):
    return render(
        request,
        "dashboard/access_denied.html",
        {"studio": studio},
        status=403,
    )


@login_required
def data_import_history(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    jobs = (
        DataImportJob.objects
        .filter(studio=studio)
        .select_related("created_by", "undone_by")
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
def data_import_job_detail(request, studio_slug, job_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    job = get_object_or_404(
        DataImportJob.objects.select_related("created_by", "undone_by"),
        pk=job_id,
        studio=studio,
    )

    rows = job.row_results.all()

    return render(
        request,
        "studios/data_import_job_detail.html",
        {
            "studio": studio,
            "role": "administrator",
            "settings_section": "data_transfer",
            "job": job,
            "rows": rows,
        },
    )


@login_required
def data_import_job_download_not_imported(request, studio_slug, job_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    job = get_object_or_404(DataImportJob, pk=job_id, studio=studio)

    if not job.not_imported_csv:
        messages.info(request, "This import does not have a not-imported CSV.")
        return redirect(
            "studios:data_import_job_detail",
            studio_slug=studio.slug,
            job_id=job.pk,
        )

    response = HttpResponse(job.not_imported_csv, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="{studio.slug}-import-{job.pk}-not-imported.csv"'
    )
    return response


@login_required
@transaction.atomic
def data_import_job_undo(request, studio_slug, job_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    job = get_object_or_404(
        DataImportJob.objects.select_for_update(),
        pk=job_id,
        studio=studio,
    )

    if request.method != "POST":
        return redirect(
            "studios:data_import_job_detail",
            studio_slug=studio.slug,
            job_id=job.pk,
        )

    if job.status == DataImportJob.Status.UNDONE:
        messages.info(request, "This import has already been undone.")
        return redirect(
            "studios:data_import_job_detail",
            studio_slug=studio.slug,
            job_id=job.pk,
        )

    undone = 0
    blocked = 0

    # Reverse in descending row/id order to reduce relationship conflicts.
    rows = (
        job.row_results
        .select_for_update()
        .filter(
            result__in=[
                DataImportRowResult.Result.CREATED,
                DataImportRowResult.Result.UPDATED,
            ]
        )
        .order_by("-id")
    )

    for row in rows:
        obj = get_imported_object(row)

        if row.result == DataImportRowResult.Result.CREATED:
            if obj is None:
                row.result = DataImportRowResult.Result.UNDO_BLOCKED
                row.undo_message = "Created record no longer exists."
                row.save(update_fields=["result", "undo_message"])
                blocked += 1
                continue

            if row.after_snapshot and not snapshot_matches(obj, row.after_snapshot):
                row.result = DataImportRowResult.Result.UNDO_BLOCKED
                row.undo_message = (
                    "This record changed after the import. Encore did not delete it."
                )
                row.save(update_fields=["result", "undo_message"])
                blocked += 1
                continue

            try:
                obj.delete()
            except Exception as exc:
                row.result = DataImportRowResult.Result.UNDO_BLOCKED
                row.undo_message = f"Encore could not delete this record safely: {exc}"
                row.save(update_fields=["result", "undo_message"])
                blocked += 1
                continue

            row.result = DataImportRowResult.Result.UNDONE
            row.undo_message = "Created record was removed."
            row.save(update_fields=["result", "undo_message"])
            undone += 1
            continue

        if row.result == DataImportRowResult.Result.UPDATED:
            if obj is None:
                row.result = DataImportRowResult.Result.UNDO_BLOCKED
                row.undo_message = "Updated record no longer exists."
                row.save(update_fields=["result", "undo_message"])
                blocked += 1
                continue

            if row.after_snapshot and not snapshot_matches(obj, row.after_snapshot):
                row.result = DataImportRowResult.Result.UNDO_BLOCKED
                row.undo_message = (
                    "This record changed after the import. Encore did not overwrite newer changes."
                )
                row.save(update_fields=["result", "undo_message"])
                blocked += 1
                continue

            try:
                restore_snapshot(obj, row.before_snapshot)
            except Exception as exc:
                row.result = DataImportRowResult.Result.UNDO_BLOCKED
                row.undo_message = f"Encore could not restore the prior values safely: {exc}"
                row.save(update_fields=["result", "undo_message"])
                blocked += 1
                continue

            row.result = DataImportRowResult.Result.UNDONE
            row.undo_message = "Previous values were restored."
            row.save(update_fields=["result", "undo_message"])
            undone += 1

    job.status = DataImportJob.Status.UNDONE if blocked == 0 else DataImportJob.Status.COMPLETED_WITH_ISSUES
    job.undone_at = timezone.now()
    job.undone_by = request.user
    job.save(update_fields=["status", "undone_at", "undone_by"])

    if blocked:
        messages.warning(
            request,
            f"Undo finished: {undone} row(s) reversed and {blocked} row(s) left unchanged for safety.",
        )
    else:
        messages.success(
            request,
            f"Import #{job.pk} was undone successfully. {undone} row(s) were reversed.",
        )

    return redirect(
        "studios:data_import_job_detail",
        studio_slug=studio.slug,
        job_id=job.pk,
    )
