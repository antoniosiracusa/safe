"""Payload Chart.js costruito lato server: {labels, datasets:[{label, data, backgroundColor}], meta}.

Regole (docs/01-architettura.md §3.3):
- la categoria "Non classificato" (`unclassified`) è sempre presente, ultima, anche a zero;
- le etichette sono ordinate come il vocabolario (sort_order) e tradotte nella lingua richiesta;
- il colore segue l'entità (indice fisso nel vocabolario), mai la posizione nella risposta;
  oltre 8 serie si accorpano in "Altri" (palette categoriale validata, 8 slot).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from safe.apps.lookups.models import UNCLASSIFIED, LookupValue

# Palette categoriale (light) dal riferimento dataviz: ordine fisso, CVD-safe sulle coppie adiacenti.
PALETTE = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948")
UNCLASSIFIED_COLOR = "#9ca3af"
OTHER_COLOR = "#6b7280"
SINGLE_SERIES_COLOR = PALETTE[0]
MAX_SERIES = 8

LABELS_I18N = {
    UNCLASSIFIED: {"it": "Non classificato", "en": "Unclassified", "de": "Nicht klassifiziert"},
    "other": {"it": "Altri", "en": "Other", "de": "Sonstige"},
    "national": {"it": "Connazionali", "en": "Nationals", "de": "Inländer"},
    "foreign": {"it": "Stranieri", "en": "Foreigners", "de": "Ausländer"},
    "events": {"it": "Eventi", "en": "Events", "de": "Ereignisse"},
    "persons": {"it": "Persone", "en": "Persons", "de": "Personen"},
    "means": {"it": "Mezzi utilizzati", "en": "Means used", "de": "Eingesetzte Mittel"},
}
WEEKDAYS = {
    "it": ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "de": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
}
MONTHS = {
    "it": ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "de": ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"],
}
SEASON_MONTHS = [6, 7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5]  # 1 giugno → 31 maggio

AGE_CLUSTERS: dict[str, list[tuple[int | None, str]]] = {
    # (limite superiore incluso, etichetta); None = nessun limite
    "standard": [
        (17, "0-17"),
        (24, "18-24"),
        (34, "25-34"),
        (44, "35-44"),
        (54, "45-54"),
        (64, "55-64"),
        (None, "65+"),
    ],
    "veneto_a01": [
        (10, "0-10"),
        (20, "11-20"),
        (30, "21-30"),
        (40, "31-40"),
        (50, "41-50"),
        (60, "51-60"),
        (70, "61-70"),
        (80, "71-80"),
        (None, "80+"),
    ],
}


def i18n(key: str, lang: str) -> str:
    entry = LABELS_I18N.get(key)
    return (entry or {}).get(lang) or (entry or {}).get("it") or key


@dataclass
class Axis:
    """Una dimensione del grafico: codici ordinati + etichette + colori (opzionale)."""

    codes: list[str]
    labels: dict[str, str]
    colors: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_lookup(cls, dimension: str, lang: str, *, with_unclassified: bool = True) -> Axis:
        items = list(LookupValue.objects.active_for_tenant().dimension(dimension))
        codes = [i.code for i in items]
        labels = {i.code: i.label(lang) for i in items}
        colors = {i.code: (i.color or PALETTE[k % MAX_SERIES]) for k, i in enumerate(items)}
        if with_unclassified:
            codes.append(UNCLASSIFIED)
            labels[UNCLASSIFIED] = i18n(UNCLASSIFIED, lang)
            colors[UNCLASSIFIED] = UNCLASSIFIED_COLOR
        return cls(codes, labels, colors)

    @classmethod
    def age_classes(cls, cluster: str, lang: str) -> Axis:
        classes = [label for _, label in AGE_CLUSTERS.get(cluster, AGE_CLUSTERS["standard"])]
        codes = [*classes, UNCLASSIFIED]
        labels = {c: c for c in classes}
        labels[UNCLASSIFIED] = i18n(UNCLASSIFIED, lang)
        return cls(codes, labels)

    @classmethod
    def from_pairs(
        cls, pairs: Iterable[tuple[str, str]], lang: str, *, with_unclassified: bool = True
    ) -> Axis:
        codes, labels, colors = [], {}, {}
        for k, (code, label) in enumerate(pairs):
            codes.append(code)
            labels[code] = label
            colors[code] = PALETTE[k % MAX_SERIES]
        if with_unclassified:
            codes.append(UNCLASSIFIED)
            labels[UNCLASSIFIED] = i18n(UNCLASSIFIED, lang)
            colors[UNCLASSIFIED] = UNCLASSIFIED_COLOR
        return cls(codes, labels, colors)


def single_series(
    axis: Axis,
    counts: dict[str | None, int],
    *,
    series_label: str,
    unit: str,
    meta: dict[str, Any] | None = None,
    limit: int | None = None,
    sort_desc: bool = False,
    color_by_label: bool = True,
) -> dict[str, Any]:
    """Un dataset: labels = categorie dell'asse. `counts` usa None per non classificato."""
    data = {code: int(counts.get(code, 0)) for code in axis.codes if code != UNCLASSIFIED}
    unclassified = int(counts.get(None, 0) + counts.get(UNCLASSIFIED, 0))
    codes = list(data.keys())
    if sort_desc:
        codes.sort(key=lambda c: -data[c])
    total_labels = len(codes)
    if limit is not None:
        codes = codes[:limit]
    if UNCLASSIFIED in axis.codes:
        codes.append(UNCLASSIFIED)
        data[UNCLASSIFIED] = unclassified
    colors = (
        [axis.colors.get(c, SINGLE_SERIES_COLOR) for c in codes] if color_by_label else SINGLE_SERIES_COLOR
    )
    if UNCLASSIFIED in codes and not color_by_label:
        colors = [UNCLASSIFIED_COLOR if c == UNCLASSIFIED else SINGLE_SERIES_COLOR for c in codes]
    payload: dict[str, Any] = {
        "labels": [axis.labels.get(c, c) for c in codes],
        "datasets": [{"label": series_label, "data": [data[c] for c in codes], "backgroundColor": colors}],
        "meta": {
            "unit": unit,
            "total": sum(data[c] for c in codes),
            "codes": codes,
            "total_labels": total_labels,
        },
    }
    if meta:
        payload["meta"].update(meta)
    return payload


def multi_series(
    x: Axis,
    series: Axis,
    counts: dict[tuple[str | None, str | None], int],
    *,
    unit: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Più dataset (serie = `series.codes`) sulle categorie `x.codes`. Oltre 8 serie con dati: "Altri"."""

    def norm(v: str | None) -> str:
        return UNCLASSIFIED if v is None else v

    grid: dict[str, dict[str, int]] = {s: dict.fromkeys(x.codes, 0) for s in series.codes}
    for (xc, sc), n in counts.items():
        xk, sk = norm(xc), norm(sc)
        if xk not in grid.get(sk, {}):
            continue
        grid[sk][xk] += int(n)

    active = [s for s in series.codes if s != UNCLASSIFIED and any(grid[s].values())]
    kept, folded = active[:MAX_SERIES], active[MAX_SERIES:]
    datasets: list[dict[str, Any]] = []
    for s in kept:
        datasets.append(
            {
                "label": series.labels.get(s, s),
                "data": [grid[s][c] for c in x.codes],
                "backgroundColor": series.colors.get(s, SINGLE_SERIES_COLOR),
                "code": s,
            }
        )
    if folded:
        other = [sum(grid[s][c] for s in folded) for c in x.codes]
        datasets.append(
            {
                "label": i18n("other", meta.get("lang", "it") if meta else "it"),
                "data": other,
                "backgroundColor": OTHER_COLOR,
                "code": "other",
            }
        )
    if UNCLASSIFIED in series.codes:
        datasets.append(
            {
                "label": series.labels[UNCLASSIFIED],
                "data": [grid[UNCLASSIFIED][c] for c in x.codes],
                "backgroundColor": UNCLASSIFIED_COLOR,
                "code": UNCLASSIFIED,
            }
        )
    payload: dict[str, Any] = {
        "labels": [x.labels.get(c, c) for c in x.codes],
        "datasets": datasets,
        "meta": {"unit": unit, "total": sum(sum(d["data"]) for d in datasets), "codes": x.codes},
    }
    if meta:
        payload["meta"].update({k: v for k, v in meta.items() if k != "lang"})
    return payload
