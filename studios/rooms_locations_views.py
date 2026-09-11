from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from studios.models import (
    Studio,
    StudioLocation,
    StudioRoom,
)

from classes.models import Class, ClassMeeting

from .forms import (
    StudioLocationForm,
    StudioRoomForm,
)


def _admin_workspace(
    request,
    studio,
):
    if request.user.is_superuser:
        return True

    return (
        request.session.get(
            "encore_workspace_role"
        )
        == "administrator"
        and request.session.get(
            "encore_workspace_studio_slug"
        )
        == studio.slug
        and request.user.studio_memberships.filter(
            studio=studio,
            role="administrator",
            is_active=True,
        ).exists()
    )


@login_required
def room_location_list(
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
        return render(
            request,
            "dashboard/access_denied.html",
            {
                "studio": studio,
            },
            status=403,
        )

    locations = (
        StudioLocation.objects
        .filter(
            studio=studio,
        )
        .prefetch_related(
            "rooms",
        )
        .order_by(
            "-is_primary",
            "name",
        )
    )

    studio_rooms = (
        StudioRoom.objects
        .filter(
            studio=studio,
            location__isnull=True,
        )
        .order_by(
            "name",
        )
    )

    return render(
        request,
        "studios/location_list.html",
        {
            "studio": studio,
            "role": "administrator",
            "locations": locations,
            "studio_rooms": studio_rooms,
            "settings_section": "locations",
        },
    )


@login_required
def location_add(
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
        return render(
            request,
            "dashboard/access_denied.html",
            {
                "studio": studio,
            },
            status=403,
        )

    form = StudioLocationForm(
        request.POST or None
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        location = form.save(
            commit=False
        )

        location.studio = studio
        location.full_clean()
        location.save()

        if location.is_primary:
            (
                StudioLocation.objects
                .filter(
                    studio=studio,
                    is_primary=True,
                )
                .exclude(
                    pk=location.pk,
                )
                .update(
                    is_primary=False,
                )
            )

        messages.success(
            request,
            "Studio location added.",
        )

        return redirect(
            "studios:location_list",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "studios/location_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "page_title": "Add Location",
            "page_intro": (
                "Add a physical studio, building, "
                "or teaching location."
            ),
            "settings_section": "locations",
            "editing": False,
        },
    )


@login_required
def room_add(
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
        return render(
            request,
            "dashboard/access_denied.html",
            {
                "studio": studio,
            },
            status=403,
        )

    initial = {}

    requested_location = (
        request.GET.get(
            "location",
            "",
        )
        .strip()
    )

    if requested_location.isdigit():
        location = (
            StudioLocation.objects
            .filter(
                studio=studio,
                pk=int(
                    requested_location
                ),
            )
            .first()
        )

        if location:
            initial[
                "location"
            ] = location

    form = StudioRoomForm(
        request.POST or None,
        studio=studio,
        initial=initial,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        room = form.save(
            commit=False
        )

        room.studio = studio
        room.full_clean()
        room.save()

        messages.success(
            request,
            "Studio room added.",
        )

        return redirect(
            "studios:location_list",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "studios/room_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "settings_section": "locations",
            "editing": False,
            "page_title": "Add Room",
        },
    )


@login_required
def location_edit(request, studio_slug, location_id):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _admin_workspace(request, studio):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    location = get_object_or_404(
        StudioLocation,
        pk=location_id,
        studio=studio,
    )

    form = StudioLocationForm(
        request.POST or None,
        instance=location,
    )

    if request.method == "POST" and form.is_valid():
        location = form.save(commit=False)
        location.studio = studio
        location.full_clean()
        location.save()

        if location.is_primary:
            (
                StudioLocation.objects
                .filter(studio=studio, is_primary=True)
                .exclude(pk=location.pk)
                .update(is_primary=False)
            )

        messages.success(request, "Physical location updated.")
        return redirect("studios:location_list", studio_slug=studio.slug)

    return render(
        request,
        "studios/location_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "location": location,
            "editing": True,
            "page_title": "Edit Physical Location",
            "page_intro": "Update this building or studio site's information.",
            "settings_section": "locations",
        },
    )


@login_required
def location_delete(request, studio_slug, location_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return render(request, "dashboard/access_denied.html", {"studio": studio}, status=403)

    location = get_object_or_404(StudioLocation, pk=location_id, studio=studio)
    if request.method != "POST":
        return redirect("studios:location_list", studio_slug=studio.slug)

    room_count = StudioRoom.objects.filter(location=location).count()
    class_count = Class.objects.filter(default_location=location).count()
    meeting_count = ClassMeeting.objects.filter(location=location).count()

    if room_count or class_count or meeting_count:
        messages.error(
            request,
            "This location is still in use. Move or remove its rooms/classes first, "
            "or edit the location and mark it inactive.",
        )
    else:
        name = location.name
        location.delete()
        messages.success(request, f"{name} was removed.")

    return redirect("studios:location_list", studio_slug=studio.slug)


@login_required
def room_edit(request, studio_slug, room_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return render(request, "dashboard/access_denied.html", {"studio": studio}, status=403)

    room = get_object_or_404(StudioRoom, pk=room_id, studio=studio)
    form = StudioRoomForm(
        request.POST or None,
        instance=room,
        studio=studio,
    )

    if request.method == "POST" and form.is_valid():
        room = form.save(commit=False)
        room.studio = studio
        room.full_clean()
        room.save()
        messages.success(request, "Room updated.")
        return redirect("studios:location_list", studio_slug=studio.slug)

    return render(
        request,
        "studios/room_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "room": room,
            "editing": True,
            "page_title": "Edit Room",
            "settings_section": "locations",
        },
    )


@login_required
def room_delete(request, studio_slug, room_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return render(request, "dashboard/access_denied.html", {"studio": studio}, status=403)

    room = get_object_or_404(StudioRoom, pk=room_id, studio=studio)
    if request.method != "POST":
        return redirect("studios:location_list", studio_slug=studio.slug)

    meeting_count = ClassMeeting.objects.filter(room=room).count()
    if meeting_count:
        messages.error(
            request,
            "This room is assigned to one or more class meetings. Reassign those meetings "
            "first, or edit the room and mark it inactive.",
        )
    else:
        name = room.name
        room.delete()
        messages.success(request, f"{name} was removed.")

    return redirect("studios:location_list", studio_slug=studio.slug)
