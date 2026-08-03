# ridership / crowding predictor (the lstm part).
# the demand curve now comes from the real dotc-mrt3 hourly ridership reports
# (see train_ridership.py). preference order at load time:
#   1. the trained keras lstm (models/ridership_lstm.keras) if tensorflow is here
#   2. the data-derived mean hourly curve (models/ridership_curve.json)
#   3. the old hand-made curve, so the engine always runs
# same interface throughout: predict(edge, hour) -> 0..1.
from __future__ import annotations

import json
from pathlib import Path

from ..routing.graph import Edge

_MODEL_DIR = Path(__file__).with_name("models")
_LSTM_PATH = _MODEL_DIR / "ridership_lstm.keras"
_CURVE_PATH = _MODEL_DIR / "ridership_curve.json"


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


# last-resort demand factor per hour (the original hand-made twin-peak curve)
_FALLBACK_DEMAND = {
    **{h: 0.45 for h in range(0, 5)},
    5: 0.70, 6: 1.05, 7: 1.40, 8: 1.45, 9: 1.20,
    10: 0.95, 11: 0.90, 12: 1.00, 13: 0.95, 14: 0.90,
    15: 0.95, 16: 1.15, 17: 1.45, 18: 1.50, 19: 1.30,
    20: 1.05, 21: 0.85, 22: 0.65, 23: 0.50,
}


def _load_real_curve() -> dict[int, float] | None:
    # mean hourly demand derived from the mrt3 reports, exported by training
    try:
        data = json.loads(_CURVE_PATH.read_text())
        return {int(h): float(v) for h, v in data["curve"].items()}
    except Exception:
        return None


def _load_lstm():
    # trained keras model; None when tensorflow or the file is missing
    try:
        import tensorflow as tf
        return tf.keras.models.load_model(_LSTM_PATH)
    except Exception:
        return None


class RidershipPredictor:
    def __init__(self) -> None:
        self._lstm = _load_lstm()
        self._curve = _load_real_curve()
        if self._lstm is not None:
            self.name = "lstm-ridership"
        elif self._curve is not None:
            self.name = "lstm-ridership (mrt3 data curve)"
        else:
            self.name = "lstm-ridership (fallback curve)"
        self.trained = self._lstm is not None
        self._lstm_cache: dict[int, float] = {}

    def _lstm_factor(self, hour: int) -> float:
        # predict the demand for this hour by feeding the previous 24 hourly
        # curve values through the lstm; cached per hour since it is per-day cyclic
        if hour in self._lstm_cache:
            return self._lstm_cache[hour]
        import numpy as np
        curve = self._curve or _FALLBACK_DEMAND
        peak = max(curve.values())
        window = [[curve.get((hour - 24 + i) % 24, 0.0) / peak] for i in range(24)]
        pred = float(self._lstm.predict(np.array([window]), verbose=0)[0][0])
        factor = pred * 1.5  # model outputs 0..1, curve scale peaks at 1.5
        self._lstm_cache[hour] = factor
        return factor

    def demand_factor(self, hour: int) -> float:
        h = hour % 24
        if self._lstm is not None:
            return self._lstm_factor(h)
        curve = self._curve or _FALLBACK_DEMAND
        # hours missing from the real curve are outside rail service (closed
        # overnight), so demand there is floor-level, not average
        return curve.get(h, min(curve.values()))

    def predict(self, edge: Edge, hour: int) -> float:
        # crowding for this edge at this hour, 0..1
        return _clamp01(edge.ridership * self.demand_factor(hour))


predictor = RidershipPredictor()
