from django.urls import path

from .admin_views import LookupAdminDetailView, LookupAdminListView
from .views import LookupsView

urlpatterns = [
    path("lookups", LookupsView.as_view(), name="lookups"),
    path("lookups/<str:dimension>", LookupAdminListView.as_view(), name="lookups-admin"),
    path("lookups/<str:dimension>/<uuid:pk>", LookupAdminDetailView.as_view(), name="lookups-admin-detail"),
]
