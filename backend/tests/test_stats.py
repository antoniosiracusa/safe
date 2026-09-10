"""Aggregatori statistici su un dataset di riferimento noto (docs/06: criterio di accettazione)."""

import datetime as dt

import pytest

from safe.apps.rescue import services
from safe.apps.rescue.models import Event, PersonEvacuationMean
from safe.apps.tenancy.context import tenant_context

from . import factories as f
from .conftest import auth, create_user

pytestmark = pytest.mark.django_db

UTC = dt.UTC


@pytest.fixture
def dataset(company, team):  # noqa: ANN001, ANN201
    """Stagione 2025/2026: 4 eventi (3 con persone). Stagione 2024/2025: 1 evento con 1 persona.

    E1 18/01/2026 (dom) LE CIAUNE, collisione, sereno: P1 F 26 IT frattura (akja→ambulanza),
       P2 M 16 PL illeso (autonomo)
    E2 03/04/2026 (ven) FERTAZZA, caduta, sereno:      P3 M 5 IT illeso (akja)
    E3 27/12/2025 (sab) senza pista, malore, meteo n.c.: P4 età n.c., genere n.c., paese n.c., elicottero
    E4 10/02/2026 (mar) LE CIAUNE, caduta, neve: nessuna persona (non valido)
    E5 15/01/2025 (mer, stagione 2024/2025) FERTAZZA, caduta: P5 F 70 DE distorsione (motoslitta)
    """
    with tenant_context(company.id):
        _, zone, ciaune = f.territory()
        fertazza = f.territory(slope_name="FERTAZZA")[2]
        e1 = f.event(team, when=dt.datetime(2026, 1, 18, 10, 5, tzinfo=UTC))
        p1 = f.person(e1)
        PersonEvacuationMean.objects.create(person=p1, mean=f.lv("evacuation_mean", "ambulance"), order=2)
        f.person(
            e1,
            age=16,
            gender=f.lv("gender", "male"),
            country_id="PL",
            diagnosis=f.lv("diagnosis", "unharmed"),
            equipment=f.lv("equipment", "snowboard"),
        )
        p2 = e1.persons.get(sequence=2)
        p2.evacuation_means.all().delete()
        PersonEvacuationMean.objects.create(person=p2, mean=f.lv("evacuation_mean", "autonomous"), order=1)
        e2 = f.event(
            team,
            when=dt.datetime(2026, 4, 3, 9, 5, tzinfo=UTC),
            slope=fertazza,
            cause=f.lv("cause", "accidental_fall"),
        )
        f.person(e2, age=5, gender=f.lv("gender", "male"), diagnosis=f.lv("diagnosis", "unharmed"))
        e3 = f.event(
            team,
            when=dt.datetime(2025, 12, 27, 13, 20, tzinfo=UTC),
            complete=False,
            zone=zone,
            cause=f.lv("cause", "illness"),
        )
        p4 = f.person(e3, complete=False)
        PersonEvacuationMean.objects.create(
            person=p4, mean=f.lv("evacuation_mean", "helicopter_118"), order=1
        )
        f.event(
            team,
            when=dt.datetime(2026, 2, 10, 11, 0, tzinfo=UTC),
            cause=f.lv("cause", "accidental_fall"),
            weather=f.lv("weather", "snow"),
        )
        e5 = f.event(
            team,
            when=dt.datetime(2025, 1, 15, 12, 0, tzinfo=UTC),
            slope=fertazza,
            cause=f.lv("cause", "accidental_fall"),
        )
        p5 = f.person(e5, age=70, country_id="DE", diagnosis=f.lv("diagnosis", "sprain"))
        p5.evacuation_means.all().delete()
        PersonEvacuationMean.objects.create(person=p5, mean=f.lv("evacuation_mean", "snowmobile"), order=1)
        for ev in Event.objects.all():
            services.compute_event_validity(ev)
        return {"ciaune": ciaune, "fertazza": fertazza}


def _series(body, label):  # noqa: ANN001, ANN201
    return next(d for d in body["datasets"] if d["label"] == label)


def test_cause_distribution_keeps_unclassified_and_lookup_order(as_admin, dataset):
    body = as_admin.get("/api/v1/stats/typology/cause?season=2025/2026").json()
    assert body["labels"][-1] == "Non classificato"
    data = dict(zip(body["meta"]["codes"], body["datasets"][0]["data"], strict=True))
    assert data["accidental_fall"] == 2 and data["collision_person"] == 1 and data["illness"] == 1
    assert data["unclassified"] == 0 and body["meta"]["total"] == 4 and body["meta"]["unit"] == "events"
    assert body["datasets"][0]["backgroundColor"][-1] == "#9ca3af"


def test_weather_counts_missing_as_unclassified(as_admin, dataset):
    body = as_admin.get("/api/v1/stats/weather/weather?season=2025/2026").json()
    data = dict(zip(body["meta"]["codes"], body["datasets"][0]["data"], strict=True))
    assert data == {**{c: 0 for c in data}, "clear": 2, "snow": 1, "unclassified": 1}


def test_age_gender_matrix(as_admin, dataset):
    body = as_admin.get("/api/v1/stats/demographics/age-gender?season=2025/2026").json()
    assert body["labels"] == ["0-17", "18-24", "25-34", "35-44", "45-54", "55-64", "65+", "Non classificato"]
    assert _series(body, "Maschile")["data"] == [2, 0, 0, 0, 0, 0, 0, 0]
    assert _series(body, "Femminile")["data"] == [0, 0, 1, 0, 0, 0, 0, 0]
    assert _series(body, "Non classificato")["data"] == [0, 0, 0, 0, 0, 0, 0, 1]
    assert body["meta"]["total"] == 4 and body["meta"]["unit"] == "persons"


def test_age_cluster_a01_and_language(as_admin, dataset):
    body = as_admin.get(
        "/api/v1/stats/demographics/age-gender?season=2025/2026&age_cluster=veneto_a01&lang=en"
    ).json()
    assert body["labels"][:3] == ["0-10", "11-20", "21-30"] and body["labels"][-1] == "Unclassified"
    assert _series(body, "Male")["data"][:2] == [1, 1]


def test_country_top_other_unclassified(as_admin, dataset):
    body = as_admin.get("/api/v1/stats/demographics/country?season=2025/2026&limit=1").json()
    assert body["labels"] == ["Italia", "Altri", "Non classificato"]
    assert body["datasets"][0]["data"] == [2, 1, 1]


def test_nationality_by_weekday(as_admin, dataset):
    body = as_admin.get("/api/v1/stats/demographics/nationality-weekday?season=2025/2026").json()
    assert body["labels"][0] == "Lunedì" and body["labels"][6] == "Domenica"
    assert _series(body, "Connazionali")["data"] == [0, 0, 0, 0, 1, 0, 1]  # ven (E2), dom (E1 P1)
    assert _series(body, "Stranieri")["data"] == [0, 0, 0, 0, 0, 0, 1]  # dom (E1 P2)
    assert _series(body, "Non classificato")["data"] == [0, 0, 0, 0, 0, 1, 0]  # sab (E3 P4)


def test_evacuation_means(as_admin, dataset):
    body = as_admin.get("/api/v1/stats/typology/evacuation-means-total?season=2025/2026").json()
    data = dict(zip(body["meta"]["codes"], body["datasets"][0]["data"], strict=True))
    assert (
        data["akja"] == 2
        and data["ambulance"] == 1
        and data["autonomous"] == 1
        and data["helicopter_118"] == 1
    )
    assert "unclassified" not in data and body["meta"]["unit"] == "means"
    first = as_admin.get("/api/v1/stats/typology/age-evacuation-mean?season=2025/2026").json()
    assert _series(first, "Akja/Toboga")["data"] == [1, 0, 1, 0, 0, 0, 0, 0]
    assert _series(first, "Elicottero 118")["data"] == [0, 0, 0, 0, 0, 0, 0, 1]
    assert first["meta"]["total"] == 4  # una riga per persona, anche con più mezzi


def test_geography_slopes_limit_and_sort(as_admin, dataset):
    body = as_admin.get("/api/v1/stats/geography/slopes?season=2025/2026&limit=1").json()
    assert body["labels"] == ["LE CIAUNE", "Non classificato"]
    assert body["datasets"][0]["data"] == [2, 1] and body["meta"]["total_labels"] == 2
    diff = as_admin.get("/api/v1/stats/geography/slope-difficulty?season=2025/2026").json()
    data = dict(zip(diff["meta"]["codes"], diff["datasets"][0]["data"], strict=True))
    assert data["blue"] == 3 and data["unclassified"] == 1
    areas = as_admin.get("/api/v1/stats/geography/ski-areas?season=2025/2026").json()
    assert areas["labels"] == ["Civetta", "Non classificato"] and areas["datasets"][0]["data"] == [4, 0]


def test_zone_table_and_annual_distribution(as_admin, dataset):
    table = as_admin.get("/api/v1/stats/zone-summary/table").json()
    assert table["columns"] == ["2024/2025", "2025/2026"]
    row = table["rows"][0]
    assert row["zone"]["name"] == "Val Fiorentina"
    assert row["cells"] == [{"events": 1, "persons": 1}, {"events": 4, "persons": 4}]
    assert table["totals"][1] == {"events": 4, "persons": 4}
    annual = as_admin.get("/api/v1/stats/zone-summary/annual-distribution?season=2025/2026").json()
    assert annual["labels"][0] == "Giu" and annual["labels"][-1] == "Mag"
    s = _series(annual, "2025/2026")["data"]
    assert s == [0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 1, 0]  # dic, gen, feb, apr
    inc = as_admin.get(
        "/api/v1/stats/zone-summary/annual-distribution?season=2025/2026&incremental=true"
    ).json()
    assert _series(inc, "2025/2026")["data"][-1] == 4


def test_season_summary_requires_advanced_and_counts(as_admin, api_client, company, team, dataset):
    body = as_admin.get("/api/v1/stats/season-summary/teams?season=2025/2026").json()
    row = body["rows"][0]
    assert row["team"]["name"] == "Squadra A"
    assert row["season_events"] == 4 and row["invalid_events"] == 2 and row["helicopter_rescues"] == 1
    assert body["totals"]["season_events"] == 4
    analyst_no_adv = create_user(company, "basic@a.test", grants=("stats.view",), team=team)
    r = auth(api_client, analyst_no_adv).get("/api/v1/stats/season-summary/teams")
    assert r.status_code == 403 and r.json()["missing"] == ["stats.advanced"]


def test_filters_apply_uniformly(as_admin, dataset, company):
    body = as_admin.get("/api/v1/stats/typology/cause?date_from=2026-04-01&date_to=2026-04-30").json()
    assert body["meta"]["total"] == 1
    body = as_admin.get("/api/v1/stats/typology/cause?season=2025/2026&valid_only=true").json()
    assert body["meta"]["total"] == 2  # E1 ed E2 sono fully_valid
    body = as_admin.get("/api/v1/stats/typology/cause?zone=00000000-0000-0000-0000-000000000000").json()
    assert body["meta"]["total"] == 0


def test_cache_invalidated_on_write(as_admin, dataset, team, company):
    url = "/api/v1/stats/typology/cause?season=2025/2026"
    first = as_admin.get(url).json()
    assert first["meta"]["cached"] is False
    assert as_admin.get(url).json()["meta"]["cached"] is True
    with tenant_context(company.id):
        f.event(team, when=dt.datetime(2026, 3, 1, 9, 0, tzinfo=UTC), cause=f.lv("cause", "illness"))
    body = as_admin.get(url).json()
    assert body["meta"]["cached"] is False and body["meta"]["total"] == 5


def test_general_kpis(as_admin, dataset):
    body = as_admin.get("/api/v1/stats/general").json()
    assert body["total_events"] == 5 and body["total_persons"] == 5 and body["total_seasons"] == 2


def test_stats_requires_permission(api_client, company, team, dataset):
    user = create_user(company, "nostats@a.test", roles=("key_custodian",), team=team)
    r = auth(api_client, user).get("/api/v1/stats/typology/cause")
    assert r.status_code == 403 and r.json()["missing"] == ["stats.view"]
