from rest_framework.routers import SimpleRouter

from .views import EventViewSet, PersonViewSet

router = SimpleRouter(trailing_slash=False)
router.register("events", EventViewSet, basename="event")
router.register("persons", PersonViewSet, basename="person")

urlpatterns = router.urls
