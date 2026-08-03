# trains the lstm ridership model (the T criterion).
# data: the dotc-mrt3 hourly ridership reports from the group data drive
# (2024 + 2025 sheets), parsed into an hourly total-entries series. the lstm
# (tensorflow/keras) looks at the last 24 hours and predicts the next hour's
# demand, normalized 0..1 against the observed peak. that predicted demand
# scales each edge's baseline crowding, same as the old demand curve did.
# also exports the observed mean hourly curve as a fallback for machines
# without tensorflow (see ridership.py).
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).with_name("data")
MODEL_DIR = Path(__file__).with_name("models")
MODEL_PATH = MODEL_DIR / "ridership_lstm.keras"
CURVE_PATH = MODEL_DIR / "ridership_curve.json"
_SEED = 11  # group 11, reproducible
_WINDOW = 24  # look back one day of hours


def parse_mrt3_sheet(path: Path) -> list[tuple[str, int, float]]:
    # pull (date, hour, total_entries) rows out of the messy report layout.
    # data rows start with a date like 01-Jan-25 and the hour block "06:00 - 06:59";
    # the second-to-last column is the formatted total entry count.
    rows: list[tuple[str, int, float]] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for cells in csv.reader(f):
            if len(cells) < 5 or not re.match(r"\d{2}-\w{3}-\d{2}", cells[0] or ""):
                continue
            m = re.match(r"(\d{2}):00", cells[1] or "")
            if not m:
                continue
            hour = int(m.group(1))
            total = (cells[-2] or "").strip().replace(",", "")
            if total in ("", "-"):
                continue
            try:
                rows.append((cells[0], hour, float(total)))
            except ValueError:
                continue
    return rows


def build_series() -> np.ndarray:
    # stitch every sheet into one hourly series (chronological within each file)
    rows: list[tuple[str, int, float]] = []
    for path in sorted(DATA_DIR.glob("mrt3_hourly_*.csv")):
        rows += parse_mrt3_sheet(path)
    if not rows:
        raise SystemExit(f"no mrt3_hourly_*.csv sheets found in {DATA_DIR}")
    return np.array([r[2] for r in rows], dtype=float)


def hourly_mean_curve() -> dict[int, float]:
    # observed mean demand per hour of day, normalized so the peak hour = 1.5
    # (same scale the old hand-made curve used). this is the no-tensorflow
    # fallback and it is derived from the real data, not guessed.
    by_hour: dict[int, list[float]] = {}
    for path in sorted(DATA_DIR.glob("mrt3_hourly_*.csv")):
        for _, hour, total in parse_mrt3_sheet(path):
            by_hour.setdefault(hour, []).append(total)
    means = {h: float(np.mean(v)) for h, v in by_hour.items()}
    peak = max(means.values())
    return {h: round(1.5 * m / peak, 3) for h, m in sorted(means.items())}


def make_windows(series: np.ndarray):
    # normalize 0..1 then slice into (24 hours in -> next hour out)
    peak = series.max()
    s = series / peak
    X, y = [], []
    for i in range(len(s) - _WINDOW):
        X.append(s[i : i + _WINDOW])
        y.append(s[i + _WINDOW])
    return np.array(X)[..., None], np.array(y), float(peak)


def train():
    import tensorflow as tf

    tf.keras.utils.set_random_seed(_SEED)
    series = build_series()
    X, y, peak = make_windows(series)
    split = int(len(X) * 0.85)
    X_tr, X_te, y_tr, y_te = X[:split], X[split:], y[:split], y[split:]

    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(_WINDOW, 1)),
        tf.keras.layers.LSTM(32),
        tf.keras.layers.Dense(16, activation="relu"),
        tf.keras.layers.Dense(1, activation="sigmoid"),
    ])
    model.compile(optimizer="adam", loss="mse", metrics=["mae"])
    model.fit(X_tr, y_tr, epochs=15, batch_size=32, verbose=2,
              validation_data=(X_te, y_te))
    loss, mae = model.evaluate(X_te, y_te, verbose=0)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model.save(MODEL_PATH)
    metrics = {
        "test_mse": round(float(loss), 5),
        "test_mae": round(float(mae), 5),
        "n_hours": int(len(series)),
        "window": _WINDOW,
        "peak_entries": int(peak),
        "source": "dotc-mrt3 hourly ridership reports (2024, 2025)",
    }
    # persist so the dashboard can show real numbers without tensorflow loaded
    (MODEL_DIR / "ridership_metrics.json").write_text(json.dumps(metrics, indent=2))
    return metrics


def export_curve():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    curve = hourly_mean_curve()
    CURVE_PATH.write_text(json.dumps({"curve": curve}, indent=2))
    return curve


if __name__ == "__main__":
    curve = export_curve()
    print("exported real hourly demand curve ->", CURVE_PATH)
    print("curve:", curve)
    try:
        m = train()
        print("trained lstm ->", MODEL_PATH)
        print("metrics:", m)
    except ImportError:
        print("tensorflow not installed; kept the data-derived curve only")
