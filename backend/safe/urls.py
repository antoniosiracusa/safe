from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny

urlpatterns = [
    path("api/v1/", include("safe.apps.core.urls")),
    path("api/v1/", include("safe.apps.authz.urls")),
    path("api/v1/", include("safe.apps.lookups.urls")),
    path("api/v1/", include("safe.apps.rescue.urls")),
    path("api/v1/", include("safe.apps.territory.urls")),
    path("api/v1/", include("safe.apps.stats.urls")),
    path("api/v1/", include("safe.apps.maps.urls")),
    path(
        "api/schema/",
        SpectacularAPIView.as_view(permission_classes=[AllowAny], authentication_classes=[]),
        name="schema",
    ),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(
            url_name="schema", permission_classes=[AllowAny], authentication_classes=[]
        ),
        name="swagger-ui",
    ),
]
