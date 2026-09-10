from rest_framework.routers import SimpleRouter

from .views import SkiAreaViewSet, SlopeViewSet, ZoneViewSet

router = SimpleRouter(trailing_slash=False)
router.register("ski-areas", SkiAreaViewSet, basename="ski-area")
router.register("zones", ZoneViewSet, basename="zone")
router.register("slopes", SlopeViewSet, basename="slope")

urlpatterns = router.urls
