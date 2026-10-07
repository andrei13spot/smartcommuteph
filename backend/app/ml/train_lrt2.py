# trains the lrt-2 ridership lstm (the T criterion for LRT-2 edges). same
# recipe as train_busway.py. the series is lrt-2 system entries per hour built
# from the lrta afc operational statistics (entries per station by time band,
# january 2024 to december 2025 plus march 2026, foi tracking LRTA-315199311699):
# each band's entries are spread evenly over its hours (05-07, 07-09, 09-17,
# 17-19, 19-22) and the hours with no service (22:00-05:00) are zero. only
# days with all five bands are used. also exports the mean hourly curve.
# parse the pdfs first: python app/ml/data/parse_lrt2_bands.py <folder> <march 2026 pdf>
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .train_ridership import MODEL_DIR, _SEED, _WINDOW, make_windows

DATA_PATH = Path(__file__).parent / "data" / "lrt2_entry_exit_bands.json"
MODEL_PATH = MODEL_DIR / "lrt2_lstm.keras"
METRICS_PATH = MODEL_DIR / "lrt2_metrics.json"
CURVE_PATH = MODEL_DIR / "lrt2_hourly_curve.json"
_BANDS = {"05-07", "07-09", "09-17", "17-19", "19-22"}


def load_days() -> list[tuple[str, list[float]]]:
    # one 24-value list (entries per hour) per complete day, in date order
    by: dict[str, dict[str, dict]] = {}
    for r in json.loads(DATA_PATH.read_text(encoding="utf-8")):
        by.setdefault(r["date"], {})[r["band"]] = r
    days = []
    for date in sorted(by):
        bands = by[date]
        if set(bands) != _BANDS:
            continue
        hours = [0.0] * 24
        for r in bands.values():
            per_hour = r["entries"] / (r["end"] - r["start"])
            for h in range(r["start"], r["end"]):
                hours[h] = per_hour
        days.append((date, hours))
    return days


def export_curve(days) -> dict[int, float]:
    # mean entries per hour over all days, service hours only, peak = 1.5
    means = {h: float(np.mean([d[h] for _, d in days])) for h in range(5, 22)}
    peak = max(means.values())
    curve = {h: round(1.5 * v / peak, 3) for h, v in means.items()}
    CURVE_PATH.write_text(json.dumps({
        "description": f"lrt-2 mean hourly entries, {days[0][0]} to {days[-1][0]} ({len(days)} days), lrta afc "
                       "operational statistics by time band, each band spread evenly over its hours; no service "
                       "outside 05:00-22:00. normalized peak = 1.5, same scale as the mrt-3 demand curve.",
        "line": "LRT-2",
        "source": "lrta foi response (tracking LRTA-315199311699): peak-offpeak entry-exit per station 2024, "
                  "audit entry-exit per station 2025, march 2026",
        "curve": {str(h): v for h, v in curve.items()},
    }, indent=2), encoding="utf-8")
    return curve


def train(days) -> dict:
    import tensorflow as tf

    tf.keras.utils.set_random_seed(_SEED)
    series = np.array([v for _, d in days for v in d], dtype=float)
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
    metrics = {
        "test_rmse": round(float(np.sqrt(loss)), 5),
        "test_mse": round(float(loss), 5),
        "test_mae": round(float(mae), 5),
        "epochs_ran": int(len(hist.history["loss"])),
        "split": "chronological 70-15-15 (train/val/holdout)",
        "n_hours": int(len(series)),
        "n_days": len(days),
        "window": _WINDOW,
        "peak_entries_per_hour": int(peak),
        "first_day": days[0][0], "last_day": days[-1][0],
        "source": "lrta afc operational statistics, entries by time band spread per hour",
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    return metrics


if __name__ == "__main__":
    days = load_days()
    print(f"{len(days)} complete days, {days[0][0]} to {days[-1][0]}")
    print("curve:", export_curve(days))
    try:
        print("metrics:", train(days))
    except ImportError:
        print("tensorflow not installed; kept the hourly curve only")
