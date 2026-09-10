# flood-risk predictor (the rfr part) plus the rainfall input.
# uses a random forest trained on the mmda flood pattern (see train_flood.py),
# fed rainfall from the pagasa ten-day forecast. if the trained model or sklearn
# is missing it falls back to the rainfall-scaled heuristic so the engine still
# runs offline. same interface either way: predict(edge, rainfall_mm) -> 0..1.
from __future__ import annotations

from pathlib import Path

from ..routing.graph import Edge

# default 24h rainfall used when there's no live pagasa value
DEFAULT_RAINFALL_MM = 8.0

# how much rainfall lifts the baseline risk per mode. rail is mostly safe,
# street modes flood easily. also the model's mode_sensitivity feature.
_MODE_SENSITIVITY = {
    "LRT-1": 0.20,
    "LRT-2": 0.20,
    "MRT-3": 0.20,
    "EDSA-Bus": 0.85,
    "Jeepney": 1.00,
}

_MODEL_PATH = Path(__file__).with_name("models") / "flood_rfr.joblib"


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


# live rainfall providers, tried in order:
#   1. pagasa tenday api - kept dormant: pagasa declined the token request
#      (government use only, see docs/pagasa-api-request.md), but if a token
#      ever lands in SCPH_PAGASA_TOKEN this path comes back to life unchanged
#   2. met norway locationforecast 2.0 (api.met.no) - the panel-requested
#      replacement: the norwegian meteorological institute's public api, no
#      key, 10-day horizon, per-block precipitation in mm for any coordinates
#   3. the offline default, so the engine always runs without internet
# SCPH_RAINFALL_PROVIDER=off disables all network fetches (tests use this).
_PAGASA_URL = "https://tenday.pagasa.dost.gov.ph/api/v1/tenday/current"
_PAGASA_PARAMS = {"province": "Metro Manila"}
_METNO_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
_METNO_PARAMS = {"lat": 14.62, "lon": 121.05}  # cubao quadrant, metro manila
# met.no requires an identifying user-agent (their terms of service)
_METNO_UA = "smartcommuteph-thesis/1.0 github.com/andrei13spot/smartcommuteph"
_CACHE_TTL_S = 3600.0  # forecast is issued daily, refetching hourly is plenty

_rain_cache: dict = {"value": None, "at": 0.0, "source": "default"}


def _extract_rainfall_mm(payload: dict) -> float | None:
    # pull the nearest-day rainfall amount out of the tenday response. the api
    # nests per-day entries under 'forecast'; we look for the first numeric
    # rainfall-ish field so a minor schema change doesn't kill the whole app.
    days = payload.get("forecast") or []
    if isinstance(days, dict):
        days = list(days.values())
    for day in days:
        if not isinstance(day, dict):
            continue
        for key in ("rainfall_mm", "rainfall", "rain_mm", "rain", "total_rainfall"):
            val = day.get(key)
            if isinstance(val, dict):
                val = val.get("total") or val.get("amount") or val.get("mm")
            if val is None:
                continue
            try:
                return float(str(val).replace("mm", "").strip())
            except ValueError:
                continue
    return None


def _metno_rainfall_24h(payload: dict) -> float | None:
    # total precipitation for the next ~24 hours, in mm. the compact format
    # gives hourly entries with next_1_hours details near-term, then coarser
    # entries with only next_6_hours. prefer the hourly blocks; if there are
    # not enough, fill the remainder with non-overlapping 6-hour blocks.
    try:
        series = payload["properties"]["timeseries"]
    except (KeyError, TypeError):
        return None
    total = 0.0
    hours = 0
    for entry in series:
        if hours >= 24:
            break
        data = entry.get("data", {})
        one = data.get("next_1_hours", {}).get("details", {}).get("precipitation_amount")
        if one is not None:
            total += float(one)
            hours += 1
            continue
        six = data.get("next_6_hours", {}).get("details", {}).get("precipitation_amount")
        if six is not None:
            total += float(six)
            hours += 6
    return round(total, 1) if hours > 0 else None


def fetch_pagasa_rainfall_mm() -> float:
    # live 24h rainfall for metro manila, cached for an hour. provider chain:
    # pagasa (dormant, token only) -> met norway (default) -> offline default.
    import os
    import time

    now = time.monotonic()
    if _rain_cache["value"] is not None and now - _rain_cache["at"] < _CACHE_TTL_S:
        return _rain_cache["value"]

    provider = os.getenv("SCPH_RAINFALL_PROVIDER", "metno").strip().lower()
    token = os.getenv("SCPH_PAGASA_TOKEN", "").strip()
    if provider != "off" and token:
        try:
            import httpx
            resp = httpx.get(
                _PAGASA_URL, params=_PAGASA_PARAMS,
                headers={"token": token, "User-Agent": "smartcommuteph-thesis/1.0"},
                timeout=10,
            )
            if resp.status_code == 200:
                mm = _extract_rainfall_mm(resp.json())
                if mm is not None:
                    _rain_cache.update(value=mm, at=now, source="pagasa tenday")
                    return mm
        except Exception:
            pass  # declined/unreachable: fall through to met norway

    if provider == "metno":
        try:
            import httpx
            resp = httpx.get(
                _METNO_URL, params=_METNO_PARAMS,
                headers={"User-Agent": _METNO_UA}, timeout=10,
            )
            if resp.status_code == 200:
                mm = _metno_rainfall_24h(resp.json())
                if mm is not None:
                    _rain_cache.update(value=mm, at=now, source="met norway locationforecast")
                    return mm
        except Exception:
            pass  # network down or schema surprise: fall through to the default

    # cache the fallback for only ~2 minutes so a recovered feed is picked up
    # quickly instead of the default squatting for the full hour ttl
    _rain_cache.update(value=DEFAULT_RAINFALL_MM, at=now - (_CACHE_TTL_S - 120.0),
                       source="default (provider off / offline)")
    return DEFAULT_RAINFALL_MM


def rainfall_source() -> str:
    # for the status endpoint, so the dashboard can say where the number came from
    return _rain_cache["source"]


def _load_model():
    # load the trained rfr once at import; None if not trained yet or no sklearn
    try:
        import joblib
        return joblib.load(_MODEL_PATH)
    except Exception:
        return None


class FloodRiskPredictor:
    def __init__(self) -> None:
        bundle = _load_model()
        self._model = bundle["model"] if bundle else None
        self.metrics = bundle["metrics"] if bundle else None
        self.name = "rfr-flood" if self._model else "rfr-flood (heuristic fallback)"
        self.trained = self._model is not None

    def _sensitivity(self, mode: str) -> float:
        return _MODE_SENSITIVITY.get(mode, 0.6)

    def _heuristic(self, edge: Edge, rainfall_mm: float) -> float:
        # rainfall scaled against a ~50mm heavy-rain reference
        rain_factor = min(rainfall_mm / 50.0, 1.0)
        risk = edge.flood_risk * (1.0 + self._sensitivity(edge.mode) * rain_factor)
        return _clamp01(risk)

    def predict(self, edge: Edge, rainfall_mm: float) -> float:
        # flood risk for this edge given the rainfall, 0..1
        if self._model is None:
            return self._heuristic(edge, rainfall_mm)
        features = [[rainfall_mm, self._sensitivity(edge.mode), edge.flood_risk]]
        return _clamp01(float(self._model.predict(features)[0]))

    def predict_batch(self, edges: list[Edge], rainfall_mm: float) -> list[float]:
        # one vectorized model call for the whole edge list. a per-edge
        # single-row predict costs ~50ms each in sklearn overhead, which made
        # every routing query take ~25s on the dense graph.
        if self._model is None:
            return [self._heuristic(e, rainfall_mm) for e in edges]
        features = [[rainfall_mm, self._sensitivity(e.mode), e.flood_risk] for e in edges]
        return [_clamp01(float(v)) for v in self._model.predict(features)]


predictor = FloodRiskPredictor()
