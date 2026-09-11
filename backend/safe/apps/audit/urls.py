from django.urls import path

from .views import AuditActionsView, AuditExportView, AuditListView

urlpatterns = [
    path("audit-logs", AuditListView.as_view(), name="audit-list"),
    path("audit-logs/actions", AuditActionsView.as_view(), name="audit-actions"),
    path("audit-logs/export", AuditExportView.as_view(), name="audit-export"),
]
