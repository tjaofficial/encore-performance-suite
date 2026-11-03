from django.urls import path

from . import views

app_name = "performance"

urlpatterns = [
    path("<slug:studio_slug>/drawing-board/<int:board_id>/venue-templates/save/", views.drawing_board_stage_template_save, name="drawing_board_stage_template_save"),
    path("<slug:studio_slug>/drawing-board/<int:board_id>/venue-templates/apply/", views.drawing_board_stage_template_apply, name="drawing_board_stage_template_apply"),
    path("<slug:studio_slug>/drawing-board/<int:board_id>/venue-templates/undo/", views.drawing_board_stage_template_undo, name="drawing_board_stage_template_undo"),
    path("<slug:studio_slug>/<int:plan_id>/view/", views.dance_choreography_viewer, name="dance_choreography_viewer"),
    path("<slug:studio_slug>/<int:plan_id>/notes/autosave/", views.dance_notes_autosave, name="dance_notes_autosave"),
    path(
        "<slug:studio_slug>/drawing-board/<int:board_id>/information/save/",
        views.drawing_board_information_save,
        name="drawing_board_information_save",
    ),
    path(
        "<slug:studio_slug>/drawing-board/<int:board_id>/dances/add/",
        views.drawing_board_dance_add,
        name="drawing_board_dance_add",
    ),
    path(
        "<slug:studio_slug>/drawing-board/<int:board_id>/songs/add/",
        views.drawing_board_song_add,
        name="drawing_board_song_add",
    ),
    path(
        "<slug:studio_slug>/drawing-board/<int:board_id>/lighting/fixtures/add/",
        views.drawing_board_lighting_fixture_add,
        name="drawing_board_lighting_fixture_add",
    ),
    path(
        "<slug:studio_slug>/drawing-board/<int:board_id>/lighting/fixtures/<int:fixture_id>/delete/",
        views.drawing_board_lighting_fixture_delete,
        name="drawing_board_lighting_fixture_delete",
    ),
    path(
        "<slug:studio_slug>/drawing-board/<int:board_id>/lighting/add/",
        views.drawing_board_lighting_cue_add,
        name="drawing_board_lighting_cue_add",
    ),
    path(
        "<slug:studio_slug>/drawing-board/<int:board_id>/lighting/<int:cue_id>/delete/",
        views.drawing_board_lighting_cue_delete,
        name="drawing_board_lighting_cue_delete",
    ),
    path("<slug:studio_slug>/drawing-board/dance/<int:plan_id>/", views.drawing_board_for_plan, name="drawing_board_for_plan"),
    path("<slug:studio_slug>/drawing-board/class/<int:class_id>/", views.drawing_board_for_class, name="drawing_board_for_class"),
    path("<slug:studio_slug>/drawing-board/<int:board_id>/", views.drawing_board_detail, name="drawing_board_detail"),
    path(
        "<slug:studio_slug>/drawing-board/<int:board_id>/copy/",
        views.drawing_board_copy_to_class,
        name="drawing_board_copy_to_class",
    ),
    path("<slug:studio_slug>/drawing-board/<int:board_id>/save/", views.drawing_board_detail_save, name="drawing_board_detail_save"),
    path("<slug:studio_slug>/drawing-board/<int:board_id>/formations/add/", views.drawing_board_detail_formation_add, name="drawing_board_detail_formation_add"),
    path("<slug:studio_slug>/drawing-board/<int:board_id>/formations/<int:formation_id>/delete/", views.drawing_board_formation_delete, name="drawing_board_formation_delete"),
    path(
        "<slug:studio_slug>/",
        views.plan_list,
        name="plan_list",
    ),
    path(
        "<slug:studio_slug>/add/",
        views.plan_create,
        name="plan_create",
    ),
    path(
        "<slug:studio_slug>/<int:plan_id>/",
        views.plan_detail,
        name="plan_detail",
    ),
    path(
        "<slug:studio_slug>/<int:plan_id>/edit/",
        views.plan_edit,
        name="plan_edit",
    ),
    path(
        "<slug:studio_slug>/<int:plan_id>/board/",
        views.drawing_board,
        name="drawing_board",
    ),
    path(
        "<slug:studio_slug>/<int:plan_id>/board/save/",
        views.drawing_board_save,
        name="drawing_board_save",
    ),
    path(
        "<slug:studio_slug>/<int:plan_id>/board/formations/add/",
        views.drawing_board_formation_add,
        name="drawing_board_formation_add",
    ),
    path(
        "<slug:studio_slug>/<int:plan_id>/formations/add/",
        views.formation_add,
        name="formation_add",
    ),
    path(
        "<slug:studio_slug>/<int:plan_id>/formations/<int:formation_id>/edit/",
        views.formation_edit,
        name="formation_edit",
    ),
    path(
        "<slug:studio_slug>/<int:plan_id>/formations/<int:formation_id>/board/",
        views.formation_board,
        name="formation_board",
    ),
    path(
        "<slug:studio_slug>/<int:plan_id>/formations/<int:formation_id>/board/save/",
        views.formation_board_save,
        name="formation_board_save",
    ),
    path(
        "<slug:studio_slug>/<int:plan_id>/formations/<int:formation_id>/duplicate/",
        views.formation_duplicate,
        name="formation_duplicate",
    ),
    path(
        "<slug:studio_slug>/<int:plan_id>/lighting/add/",
        views.lighting_add,
        name="lighting_add",
    ),
    path(
        "<slug:studio_slug>/<int:plan_id>/lighting/<int:cue_id>/edit/",
        views.lighting_edit,
        name="lighting_edit",
    ),
    path(
        "<slug:studio_slug>/<int:plan_id>/prep/add/",
        views.prep_add,
        name="prep_add",
    ),
    path(
        "<slug:studio_slug>/<int:plan_id>/prep/<int:prep_id>/edit/",
        views.prep_edit,
        name="prep_edit",
    ),
]
