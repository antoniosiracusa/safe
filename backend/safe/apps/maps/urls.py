from django.urls import path

from . import views as v

urlpatterns = [
    path("map/events.geojson", v.EventsGeoJSONView.as_view(), name="map-events"),
    path("map/ski-areas.geojson", v.SkiAreasGeoJSONView.as_view(), name="map-ski-areas"),
    path("map/slopes.geojson", v.SlopesGeoJSONView.as_view(), name="map-slopes"),
    path("map/lifts.geojson", v.LiftsGeoJSONView.as_view(), name="map-lifts"),
    path("map/styles", v.StylesView.as_view(), name="map-styles"),
]
