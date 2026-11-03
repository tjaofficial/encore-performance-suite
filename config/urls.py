from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", include("marketing.urls")),
    path("accounts/", include("accounts.urls")),
    path("calendar/", include("scheduling.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("attendance/", include("attendance.urls")),
    path("classes/", include("classes.urls")),
    path("students/", include("students.urls")),
    path("families/", include("families.urls")),
    path("instructors/", include("instructors.urls")),
    path("enrollments/", include("enrollments.urls")),
    path("billing/", include("billing.urls")),
    path("evaluations/", include("evaluations.urls")),
    path("resources/", include("resources.urls")),
    path("performance/", include("performance.urls")),
    path("communications/", include("communications.urls")),
    path("reports/", include("reports.urls")),
    path("registration/", include("registration_portal.urls")),
    path("studios/", include("studios.urls")),
    path("tasks/", include("tasks.urls")),
    path("time/", include("timekeeping.urls")),
    path("costumes/", include("costumes.urls")),
    path("support/", include("support_center.urls")),
]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
