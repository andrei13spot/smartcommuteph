# trains the lrt-1 ridership lstm (the T criterion for LRT-1 edges).
# lrmc did not give us hourly or time-band counts, so the series is
# reconstructed from aggregate data and the metrics say so:
#   - the monthly lrt-1 passenger totals come from psa table 13-2 (real, 2024)
#   - each month's total is spread over its days and hours using the real
#     mrt-3 hourly entries for the same dates (mrt3_hourly_2024.csv), so an
#     lrt-1 hour = psa month total x (mrt-3 entries that hour / mrt-3 month total)
# so the volume is lrt-1's and the hour-by-hour shape is borrowed from mrt-3,
# the closest line we have hourly data for. only 2024 has both sources.
# same lstm recipe as train_lrt2.py. also exports the mean hourly curve.
from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

import numpy as np

from .train_ridership import DATA_DIR, MODEL_DIR, _SEED, _WINDOW, make_windows, parse_mrt3_sheet

PSA_PATH = Path(__file__).parent / "data" / "psa_table_13-2_rail_ridership.csv"
MODEL_PATH = MODEL_DIR / "lrt1_lstm.keras"
METRICS_PATH = MODEL_DIR / "lrt1_metrics.json"
CURVE_PATH = MODEL_DIR / "lrt1_hourly_curve.json"
_YEAR = 2024


def psa_monthly_lrt1() -> dict[str, float]:
    # "2024-01" -> lrt-1 passengers that month (psa reports millions)
    rows = list(csv.reader(open(PSA_PATH, encoding="utf-8")))
    head = rows[0]
    for r in rows[1:]:
        if "LRT Line 1" in r[0] and r[1].startswith("Total Number of Passengers"):
            out = {}
            for label, v in zip(head[2:], r[2:]):
                d = dt.datetime.strptime(label, "%Y %B")
                out[f"{d.year}-{d.month:02d}"] = float(v) * 1_000_000
            return out
    raise SystemExit("lrt-1 passenger row not found in the psa table")


def load_days() -> list[tuple[str, list[float]]]:
    psa = psa_monthly_lrt1()
    mrt: dict[str, list[float]] = {}
    for date, hour, total in parse_mrt3_sheet(DATA_DIR / f"mrt3_hourly_{_YEAR}.csv"):
        iso = dt.datetime.strptime(date, "%d-%b-%y").strftime("%Y-%m-%d")
        mrt.setdefault(iso, [0.0] * 24)[hour] += total
    month_total: dict[str, float] = {}
    for iso, hours in mrt.items():
        month_total[iso[:7]] = month_total.get(iso[:7], 0.0) + sum(hours)
    days = []
    for iso in sorted(mrt):
        m = iso[:7]
        if m not in psa or not month_total.get(m):
            continue
        k = psa[m] / month_total[m]
        days.append((iso, [round(v * k, 1) for v in mrt[iso]]))
    return days


def export_curve(days) -> dict[int, float]:
    means = {h: float(np.mean([d[h] for _, d in days])) for h in range(24)}
    means = {h: v for h, v in means.items() if v > 0}
    peak = max(means.values())
    curve = {h: round(1.5 * v / peak, 3) for h, v in means.items()}
    CURVE_PATH.write_text(json.dumps({
        "description": f"lrt-1 mean hourly entries, {days[0][0]} to {days[-1][0]} ({len(days)} days), "
                       "reconstructed: psa monthly lrt-1 passenger totals spread over the hours with the real "
                       "mrt-3 hourly share for the same dates. normalized peak = 1.5.",
        "line": "LRT-1",
        "source": "psa table 13-2 (lrt-1 monthly passengers, 2024) x dotr mrt-3 hourly ridership 2024",
        "reconstructed": True,
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
        "reconstructed": True,
        "source": "reconstructed from aggregate data: psa monthly lrt-1 passenger totals spread per hour "
                  "with the real mrt-3 hourly share for the same dates (no lrt-1 hourly data released)",
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    return metrics


if __name__ == "__main__":
    days = load_days()
    print(f"{len(days)} days, {days[0][0]} to {days[-1][0]}")
    print("psa check, jan 2024 total:", round(sum(sum(d) for i, d in days if i.startswith("2024-01"))))
    print("curve:", export_curve(days))
    try:
        print("metrics:", train(days))
    except ImportError:
        print("tensorflow not installed; kept the hourly curve only")
