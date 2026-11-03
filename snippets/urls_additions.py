
# Add these imports near your existing imports in studios/urls.py:
from . import data_transfer_history_views

# Add these paths to urlpatterns:
path(
    "<slug:studio_slug>/settings/data-transfer/history/",
    data_transfer_history_views.data_import_history,
    name="data_import_history",
),
path(
    "<slug:studio_slug>/settings/data-transfer/history/<int:job_id>/",
    data_transfer_history_views.data_import_job_detail,
    name="data_import_job_detail",
),
path(
    "<slug:studio_slug>/settings/data-transfer/history/<int:job_id>/not-imported.csv",
    data_transfer_history_views.data_import_job_download_not_imported,
    name="data_import_job_download_not_imported",
),
path(
    "<slug:studio_slug>/settings/data-transfer/history/<int:job_id>/undo/",
    data_transfer_history_views.data_import_job_undo,
    name="data_import_job_undo",
),
