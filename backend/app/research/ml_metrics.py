# accuracy metrics for the predictive models, shown on the dashboard.
# rfr metrics come from its actual holdout test set (saved at training time in
# the joblib bundle). lstm metrics are read from the json its training run
# writes, so the dashboard shows real numbers even without tensorflow loaded.
import json
from pathlib import Path

from ..ml import flood, ridership

_LSTM_METRICS = Path(__file__).parents[1] / "ml" / "models" / "ridership_metrics.json"
_BUSWAY_METRICS = Path(__file__).parents[1] / "ml" / "models" / "busway_metrics.json"
_LRT2_METRICS = Path(__file__).parents[1] / "ml" / "models" / "lrt2_metrics.json"


def ml_metrics() -> dict:
    fp, rp = flood.predictor, ridership.predictor

    rfr = {"key": "rfr", "name": "RFR · Flood Risk", "criterion": "R - flood"}
    if fp.metrics:
        rfr.update(rmse=fp.metrics.get("rmse"), r2=fp.metrics["r2"], mae=fp.metrics["mae"],
                   detail=f"{fp.metrics['n_train']} train / {fp.metrics['n_test']} test, "
                          "features: rainfall, mode sensitivity, base exposure",
                   status="trained")
    else:
        rfr.update(rmse=None, mae=None, detail="model file missing, heuristic fallback", status="fallback")

    lstm = {
        "key": "lstm", "name": "LSTM · Ridership", "criterion": "T - ridership",
        "detail": "dotc-mrt3 hourly ridership reports (2024-2025)",
        "status": "trained" if rp.trained else "data-derived curve",
    }
    try:
        m = json.loads(_LSTM_METRICS.read_text())
        lstm.update({"rmse": m.get("test_rmse"), "mse": m["test_mse"], "mae": m["test_mae"],
                     "detail": f"{m['n_hours']} hourly obs, 24h window, {m['source']}"})
        lstm["status"] = "trained"
    except Exception:
        pass

    models = [lstm, rfr]
    # the busway lstm card appears only once train_busway.py has produced its
    # metrics, so nothing changes on machines without the digitized data
    try:
        b = json.loads(_BUSWAY_METRICS.read_text())
        models.append({
            "key": "busway", "name": "LSTM · Busway Ridership", "criterion": "T - ridership (EDSA-Bus)",
            "rmse": b.get("test_rmse"), "mse": b.get("test_mse"), "mae": b.get("test_mae"),
            "detail": f"{b.get('n_hours')} hourly obs over {b.get('n_days')} days, "
                      f"{', '.join(b.get('stations') or [])} station, dotr tally sheets digitized",
            "status": "trained" if "EDSA-Bus" in getattr(rp, "_line_lstms", {}) else "data-derived curve",
        })
    except Exception:
        pass

    try:
        m2 = json.loads(_LRT2_METRICS.read_text())
        models.append({
            "key": "lrt2", "name": "LSTM · LRT-2 Ridership", "criterion": "T - ridership (LRT-2)",
            "rmse": m2.get("test_rmse"), "mse": m2.get("test_mse"), "mae": m2.get("test_mae"),
            "detail": f"{m2.get('n_hours')} hourly obs over {m2.get('n_days')} days, "
                      "lrta entry/exit by time band (2024-2026)",
            "status": "trained" if "LRT-2" in getattr(rp, "_line_lstms", {}) else "data-derived curve",
        })
    except Exception:
        pass

    return {
        "models": models,
        "metric": "holdout test set at training time",
        "note": "rfr metrics are live from the saved model bundle",
    }
