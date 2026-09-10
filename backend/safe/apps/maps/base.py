from drf_spectacular.utils import OpenApiParameter

FILTER_PARAMS = [
    OpenApiParameter("team", str, many=True, required=False),
    OpenApiParameter("season", str, required=False),
    OpenApiParameter("date_from", str, required=False),
    OpenApiParameter("date_to", str, required=False),
    OpenApiParameter("ski_area", str, required=False),
    OpenApiParameter("zone", str, required=False),
    OpenApiParameter("valid_only", bool, required=False),
]
