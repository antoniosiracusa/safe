from django.urls import path

from .filters import FilterOptionsView
from .views import HealthView

urlpatterns = [
    path("health", HealthView.as_view(), name="health"),
    path("filters/options", FilterOptionsView.as_view(), name="filter-options"),
]
