from django.urls import path

from .views import EventReportView

urlpatterns = [path("events/<uuid:pk>/report.pdf", EventReportView.as_view(), name="event-report")]
