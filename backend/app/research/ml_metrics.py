# accuracy metrics for the predictive models, shown on the dashboard.
# rfr metrics come from its actual holdout test set (saved at training time in
# the joblib bundle). lstm metrics are read from the json its training run
# writes, so the dashboard shows real numbers even without tensorflow loaded.
import json
from pathlib import Path

from ..ml import flood, ridership

_LSTM_METRICS = Path(__file__).parents[1] / "ml" / "models" / "ridership_metrics.json"


def ml_metrics() -> dict:
    fp, rp = flood.predictor, ridership.predictor

    if fp.metrics:
        rfr = {
            "key": "rfr", "name": "RFR · Flood Risk", "criterion": "R - flood",
            "r2": fp.metrics["r2"], "mae": fp.metrics["mae"],
            "detail": f"{fp.metrics['n_train']} train / {fp.metrics['n_test']} test, "
                      "features: rainfall, mode sensitivity, base exposure",
            "status": "trained",
        }
    else:
        rfr = {
            "key": "rfr", "name": "RFR · Flood Risk", "criterion": "R - flood",
            "rmse": None, "mae": None, "detail": "model file missing, heuristic fallback",
            "status": "fallback",
        }

    lstm = {
        "key": "lstm", "name": "LSTM · Ridership", "criterion": "T - ridership",
        "detail": "dotc-mrt3 hourly ridership reports (2024-2025)",
        "status": "trained" if rp.trained else "data-derived curve",
    }
    try:
        m = json.loads(_LSTM_METRICS.read_text())
        lstm.update({"mse": m["test_mse"], "mae": m["test_mae"],
                     "detail": f"{m['n_hours']} hourly obs, 24h window, {m['source']}"})
        lstm["status"] = "trained"
    except Exception:
        pass

    return {
        "models": [lstm, rfr],
        "metric": "holdout test set at training time",
        "note": "rfr metrics are live from the saved model bundle",
    }
