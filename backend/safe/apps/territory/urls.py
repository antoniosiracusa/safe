from rest_framework.routers import SimpleRouter

from .views import LiftViewSet, SkiAreaViewSet, SlopeViewSet, ZoneViewSet

router = SimpleRouter(trailing_slash=False)
router.register("ski-areas", SkiAreaViewSet, basename="ski-area")
router.register("zones", ZoneViewSet, basename="zone")
router.register("slopes", SlopeViewSet, basename="slope")
router.register("lifts", LiftViewSet, basename="lift")

urlpatterns = router.urls
