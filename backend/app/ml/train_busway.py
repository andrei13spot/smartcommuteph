# trains the edsa busway ridership lstm (the T criterion for EDSA-Bus edges).
# same recipe as train_ridership.py, but the series is the hourly passenger
# count at one busway station, digitized from the dotr security detachment
# tally sheets (data/edsa_busway_hourly.csv, see data/README_edsa_busway.md).
# also exports the mean hourly curve the engine uses when tensorflow is not
# installed (models/busway_hourly_curve.json).
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from .train_ridership import MODEL_DIR, _SEED, _WINDOW, make_windows

DATA_PATH = Path(__file__).parent / "data" / "edsa_busway_hourly.csv"
MODEL_PATH = MODEL_DIR / "busway_lstm.keras"
METRICS_PATH = MODEL_DIR / "busway_metrics.json"
CURVE_PATH = MODEL_DIR / "busway_hourly_curve.json"


def load_rows(verified_only: bool = True) -> list[dict]:
    # (timestamp, hour, boardings) rows in time order. by default only days
    # whose 24 cells add up to the handwritten total are used.
    rows = []
    with open(DATA_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if not r.get("boardings"):
                continue
            if verified_only and r.get("day_status") != "verified":
                continue
            rows.append({"timestamp": r["timestamp"], "hour": int(r["hour"]),
                         "boardings": float(r["boardings"]), "station": r.get("station", ""),
                         "service_date": r.get("service_date", "")})
    rows.sort(key=lambda r: r["timestamp"])
    if not rows:
        raise SystemExit(f"no usable rows in {DATA_PATH}")
    return rows


def hourly_mean_curve(rows: list[dict]) -> dict[int, float]:
    # mean boardings per clock hour, normalized so the peak hour = 1.5 (the
    # same scale as the mrt-3 demand curve)
    by: dict[int, list[float]] = {}
    for r in rows:
        by.setdefault(r["hour"], []).append(r["boardings"])
    means = {h: float(np.mean(v)) for h, v in by.items()}
    peak = max(means.values())
    return {h: round(1.5 * m / peak, 3) for h, m in sorted(means.items())}


def export_curve(rows: list[dict]) -> dict[int, float]:
    curve = hourly_mean_curve(rows)
    days = {r["timestamp"][:10] for r in rows}
    stations = sorted({r["station"] for r in rows if r["station"]})
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    CURVE_PATH.write_text(json.dumps({
        "description": f"edsa busway mean hourly boardings at {', '.join(stations) or 'the busway'}, "
                       f"{min(days)} to {max(days)} ({len(days)} station-days digitized from the dotr "
                       "security detachment tally sheets, formal data request). normalized peak = 1.5, "
                       "same scale as the mrt-3 demand curve.",
        "line": "EDSA-Bus",
        "curve": curve,
    }, indent=2), encoding="utf-8")
    return curve


def train(rows: list[dict]) -> dict:
    import tensorflow as tf

    tf.keras.utils.set_random_seed(_SEED)
    series = np.array([r["boardings"] for r in rows], dtype=float)
    X, y, peak = make_windows(series)
    s1, s2 = int(len(X) * 0.70), int(len(X) * 0.85)
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(_WINDOW, 1)),
        tf.keras.layers.LSTM(32),
        tf.keras.layers.Dense(16, activation="relu"),
        tf.keras.layers.Dense(1, activation="sigmoid"),
    ])
    model.compile(optimizer="adam", loss="mse", metrics=["mae"])
    early = tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=8, restore_best_weights=True)
    hist = model.fit(X[:s1], y[:s1], epochs=60, batch_size=32, verbose=2,
                     validation_data=(X[s1:s2], y[s1:s2]), callbacks=[early])
    loss, mae = model.evaluate(X[s2:], y[s2:], verbose=0)
    model.save(MODEL_PATH)
    days = {r.get("service_date") or r["timestamp"][:10] for r in rows}  # service day runs 06:00 to 05:59
    metrics = {
        "test_rmse": round(float(np.sqrt(loss)), 5),
        "test_mse": round(float(loss), 5),
        "test_mae": round(float(mae), 5),
        "epochs_ran": int(len(hist.history["loss"])),
        "split": "chronological 70-15-15 (train/val/holdout)",
        "n_hours": int(len(series)),
        "n_days": len(days),
        "window": _WINDOW,
        "peak_boardings": int(peak),
        "first_day": min(days), "last_day": max(days),
        "stations": sorted({r["station"] for r in rows if r["station"]}),
        "source": "dotr edsa busway security detachment hourly tally sheets, digitized",
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    return metrics


if __name__ == "__main__":
    rows = load_rows()
    print(f"{len(rows)} verified hourly rows, {len({r['timestamp'][:10] for r in rows})} days")
    print("curve:", export_curve(rows))
    try:
        print("metrics:", train(rows))
    except ImportError:
        print("tensorflow not installed; kept the hourly curve only")
