from django.urls import path

from . import views

app_name = "scheduling"

urlpatterns = [
    path("<slug:studio_slug>/time-off/mine/", views.time_off_my_requests, name="time_off_my_requests"),
    path("<slug:studio_slug>/time-off/mine/<int:request_id>/edit/", views.time_off_request_change, name="time_off_request_change"),
    path(
        "<slug:studio_slug>/",
        views.calendar_page,
        name="calendar",
    ),
    path(
        "<slug:studio_slug>/feed/",
        views.calendar_feed,
        name="calendar_feed",
    ),
    path(
        "<slug:studio_slug>/events/add/",
        views.event_create,
        name="event_create",
    ),
    path(
        "<slug:studio_slug>/events/<int:event_id>/",
        views.event_detail,
        name="event_detail",
    ),
    path(
        "<slug:studio_slug>/events/<int:event_id>/edit/",
        views.event_update,
        name="event_update",
    ),
    path(
        "<slug:studio_slug>/events/<int:event_id>/delete/",
        views.event_delete,
        name="event_delete",
    ),
    path(
        "<slug:studio_slug>/categories/add/",
        views.category_create,
        name="category_create",
    ),
    path(
        "<slug:studio_slug>/preferences/",
        views.preference_update,
        name="preference_update",
    ),

    path(
        "<slug:studio_slug>/time-off/request/",
        views.time_off_request_create,
        name="time_off_request_create",
    ),
    path(
        "<slug:studio_slug>/time-off/manage/",
        views.time_off_admin_list,
        name="time_off_admin_list",
    ),
    path(
        "<slug:studio_slug>/time-off/<int:request_id>/review/",
        views.time_off_admin_review,
        name="time_off_admin_review",
    ),
    path(
        "<slug:studio_slug>/time-off/<int:request_id>/coverage/",
        views.time_off_coverage,
        name="time_off_coverage",
    ),
]
