from django.urls import path

from . import views as v

urlpatterns = [
    path("exports/regional/preview", v.RegionalPreviewView.as_view(), name="export-regional-preview"),
    path("exports/regional", v.RegionalExportView.as_view(), name="export-regional"),
    path("exports/dataset", v.DatasetExportView.as_view(), name="export-dataset"),
    path("exports/administrative-areas", v.AdministrativeAreasView.as_view(), name="export-areas"),
    path("exports", v.ExportListView.as_view(), name="export-list"),
]
