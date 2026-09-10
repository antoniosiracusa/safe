from django.urls import path

from . import views as v

urlpatterns = [
    path("stats/zone-summary/annual-distribution", v.AnnualDistributionView.as_view()),
    path("stats/zone-summary/table", v.ZoneTableView.as_view()),
    path("stats/demographics/age-gender", v.AgeGenderView.as_view()),
    path("stats/demographics/country", v.CountryView.as_view()),
    path("stats/demographics/nationality-weekday", v.NationalityWeekdayView.as_view()),
    path("stats/demographics/age-diagnosis", v.AgeDiagnosisView.as_view()),
    path("stats/demographics/age-injury-place", v.AgeInjuryPlaceView.as_view()),
    path("stats/typology/age-cause", v.AgeCauseView.as_view()),
    path("stats/typology/cause", v.CauseView.as_view()),
    path("stats/typology/age-equipment", v.AgeEquipmentView.as_view()),
    path("stats/typology/age-insurance", v.AgeInsuranceView.as_view()),
    path("stats/typology/age-evacuation-mean", v.AgeEvacuationMeanView.as_view()),
    path("stats/typology/evacuation-means-total", v.EvacuationMeansTotalView.as_view()),
    path("stats/geography/ski-areas", v.SkiAreasView.as_view()),
    path("stats/geography/slope-difficulty", v.SlopeDifficultyView.as_view()),
    path("stats/geography/slopes", v.SlopesView.as_view()),
    path("stats/weather/weather", v.WeatherView.as_view()),
    path("stats/weather/snow", v.SnowView.as_view()),
    path("stats/weather/wind", v.WindView.as_view()),
    path("stats/weather/visibility", v.VisibilityView.as_view()),
    path("stats/season-summary/teams", v.SeasonSummaryView.as_view()),
    path("stats/general", v.GeneralView.as_view()),
]
