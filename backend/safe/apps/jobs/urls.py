from django.urls import path

from .views import JobDownloadView, JobListView, JobView

urlpatterns = [
    path("jobs", JobListView.as_view(), name="job-list"),
    path("jobs/<uuid:pk>", JobView.as_view(), name="job-detail"),
    path("jobs/<uuid:pk>/download", JobDownloadView.as_view(), name="job-download"),
]
