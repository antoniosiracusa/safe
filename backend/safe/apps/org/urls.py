from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import RolesView, TeamViewSet, UserViewSet

router = SimpleRouter(trailing_slash=False)
router.register("teams", TeamViewSet, basename="team")
router.register("users", UserViewSet, basename="user")

urlpatterns = [path("roles", RolesView.as_view(), name="roles"), *router.urls]
