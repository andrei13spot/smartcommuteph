# flood-risk predictor (the rfr part) plus the rainfall input.
# the real model will be a random forest trained on mmda flood data, fed live
# rainfall from the pagasa ten-day forecast. for now this scales each edge's
# baseline by a rainfall factor, street modes get hit harder than elevated rail.
# same interface: predict(edge, rainfall_mm) -> 0..1.
from __future__ import annotations

from ..routing.graph import Edge

# default 24h rainfall used when there's no live pagasa value
DEFAULT_RAINFALL_MM = 8.0

# how much rainfall lifts the baseline risk per mode. rail is mostly safe,
# street modes flood easily.
_MODE_SENSITIVITY = {
    "LRT-1": 0.20,
    "LRT-2": 0.20,
    "MRT-3": 0.20,
    "EDSA-Bus": 0.85,
    "Jeepney": 1.00,
}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def fetch_pagasa_rainfall_mm() -> float:
    # stand-in for the pagasa ten-day forecast call. returns the default for now
    # so things run offline; swap in the http call once we have the api key.
    return DEFAULT_RAINFALL_MM


class FloodRiskPredictor:
    name = "rfr-flood"

    def predict(self, edge: Edge, rainfall_mm: float) -> float:
        # flood risk for this edge given the rainfall, 0..1
        sensitivity = _MODE_SENSITIVITY.get(edge.mode, 0.6)
        # rainfall scaled against a ~50mm heavy-rain reference
        rain_factor = min(rainfall_mm / 50.0, 1.0)
        risk = edge.flood_risk * (1.0 + sensitivity * rain_factor)
        return _clamp01(risk)


predictor = FloodRiskPredictor()
