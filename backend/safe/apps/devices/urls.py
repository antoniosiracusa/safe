from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import DeviceStatusView, DeviceViewSet

router = SimpleRouter(trailing_slash=False)
router.register("devices", DeviceViewSet, basename="device")

urlpatterns = [path("devices/summary", DeviceStatusView.as_view(), name="device-summary"), *router.urls]
