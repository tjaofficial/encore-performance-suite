from django.urls import path

from . import views
from . import music_reviews

app_name = "resources"

urlpatterns = [
    path("<slug:studio_slug>/video-manager/", views.video_manager, name="video_manager"),
    path("<slug:studio_slug>/dance/<int:plan_id>/videos/", views.dance_video_manager, name="dance_video_manager"),
    path("<slug:studio_slug>/music/<int:resource_id>/stream/", music_reviews.music_file, name="music_file"),
    path("<slug:studio_slug>/music-manager/", music_reviews.music_manager, name="music_manager"),
    path("<slug:studio_slug>/music-manager/<int:resource_id>/review/", music_reviews.music_review, name="music_review"),

    path(
        "<slug:studio_slug>/",
        views.resource_list,
        name="resource_list",
    ),
    path(
        "<slug:studio_slug>/add/",
        views.resource_create,
        name="resource_create",
    ),
    path(
        "<slug:studio_slug>/music/reuse/",
        views.resource_reuse_music,
        name="resource_reuse_music",
    ),
    path(
        "<slug:studio_slug>/<int:resource_id>/edit/",
        views.resource_edit,
        name="resource_edit",
    ),
]
