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
    path("api/v1/", include("safe.apps.jobs.urls")),
    path("api/v1/", include("safe.apps.reports.urls")),
    path("api/v1/", include("safe.apps.exports.urls")),
    path("api/v1/", include("safe.apps.org.urls")),
    path("api/v1/", include("safe.apps.devices.urls")),
    path("api/v1/", include("safe.apps.tenancy.urls")),
    path("api/v1/", include("safe.apps.crypto.urls")),
    path("api/v1/", include("safe.apps.audit.urls")),
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
