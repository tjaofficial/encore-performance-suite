from django.contrib import admin

from .models import (
    ChoreographyPlan,
    DrawingBoard,
    DrawingBoardLightingCue,
    DrawingBoardLightingFixture,
    Formation,
    FormationTransition,
    LightingCue,
    PerformancePrepItem,
)


class FormationInline(admin.TabularInline):
    model = Formation
    extra = 0


class LightingCueInline(admin.TabularInline):
    model = LightingCue
    extra = 0


class PerformancePrepItemInline(admin.TabularInline):
    model = PerformancePrepItem
    extra = 0


@admin.register(ChoreographyPlan)
class ChoreographyPlanAdmin(admin.ModelAdmin):
    list_display = (
        "class_instance",
        "studio",
        "title",
        "song_title",
        "updated_at",
    )

    list_filter = (
        "studio",
        "class_instance__season",
    )

    search_fields = (
        "title",
        "song_title",
        "artist",
        "class_instance__name",
    )

    inlines = [
        FormationInline,
        LightingCueInline,
        PerformancePrepItemInline,
    ]


admin.site.register(Formation)
admin.site.register(LightingCue)
admin.site.register(PerformancePrepItem)



@admin.register(DrawingBoard)
class DrawingBoardAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "studio",
        "class_instance",
        "performance_plan",
        "updated_at",
    )

    list_filter = (
        "studio",
    )

    search_fields = (
        "title",
        "class_instance__name",
        "performance_plan__title",
    )


@admin.register(DrawingBoardLightingCue)
class DrawingBoardLightingCueAdmin(admin.ModelAdmin):
    list_display = (
        "board",
        "cue_number",
        "name",
        "time_seconds",
        "fade_seconds",
        "is_blackout",
    )

    list_filter = (
        "board__studio",
        "is_blackout",
    )

    search_fields = (
        "board__title",
        "name",
        "notes",
    )


@admin.register(FormationTransition)
class FormationTransitionAdmin(admin.ModelAdmin):
    list_display = (
        "board",
        "from_formation",
        "to_formation",
        "duration_seconds",
    )


@admin.register(DrawingBoardLightingFixture)
class DrawingBoardLightingFixtureAdmin(admin.ModelAdmin):
    list_display = (
        "board",
        "fixture_number",
        "label",
        "fixture_type",
        "x",
        "y",
    )
    list_filter = (
        "board__studio",
        "fixture_type",
    )
    search_fields = (
        "board__title",
        "label",
        "notes",
    )
