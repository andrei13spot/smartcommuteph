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


def fetch_pagasa_rainfall_mm() -> float:
    # stand-in for the pagasa ten-day forecast call. returns the default for now
    # so things run offline; swap in the http call once we have the api key.
    return DEFAULT_RAINFALL_MM


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


predictor = FloodRiskPredictor()
