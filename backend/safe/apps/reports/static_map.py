"""Immagine statica della posizione dell'evento (Mapbox Static Images API). Nessun dato personale."""

from __future__ import annotations

import base64
import logging
from urllib.parse import quote

import requests
from django.conf import settings

log = logging.getLogger(__name__)


def static_map_data_uri(
    lon: float, lat: float, *, zoom: float = 14.5, size: tuple[int, int] = (500, 400)
) -> str | None:
    token = settings.MAPBOX_TOKEN
    if not token:
        return None
    marker = quote(f"pin-l+c8102e({lon:.6f},{lat:.6f})", safe="+(),")
    url = (
        f"https://api.mapbox.com/styles/v1/mapbox/outdoors-v12/static/{marker}/"
        f"{lon:.6f},{lat:.6f},{zoom},0/{size[0]}x{size[1]}@2x"
    )
    try:
        r = requests.get(
            url, params={"access_token": token, "attribution": "true", "logo": "true"}, timeout=10
        )
        r.raise_for_status()
    except requests.RequestException as exc:
        log.warning("mappa statica non disponibile: %s", exc)
        return None
    return "data:image/png;base64," + base64.b64encode(r.content).decode()
