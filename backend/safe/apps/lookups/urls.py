from django.urls import path

from .views import LookupsView

urlpatterns = [path("lookups", LookupsView.as_view(), name="lookups")]
