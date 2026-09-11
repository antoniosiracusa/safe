from django.urls import path

from .views import CompanyView, RetentionRunView, RetentionView

urlpatterns = [
    path("company", CompanyView.as_view(), name="company"),
    path("company/retention", RetentionView.as_view(), name="company-retention"),
    path("company/retention/run", RetentionRunView.as_view(), name="company-retention-run"),
]
