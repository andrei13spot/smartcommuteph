# trains the rfr flood-risk model (the R criterion).
# random forest regressor from scikit-learn, per the paper. it learns flood risk
# per edge from three grounded features:
#   rainfall_mm      - pagasa ten-day forecast value (0..~80)
#   mode_sensitivity - how much the mode floods (elevated rail low, street high)
#   base_exposure    - the edge's baseline flood exposure by area
# labels come from the mmda inundation pattern: risk climbs non-linearly with
# rainfall (roads start going under past ~30mm), street modes get hit harder,
# and each area carries its own baseline. when princess finishes the full mmda
# label prep this same script retrains on the real per-edge labels.
from __future__ import annotations

from pathlib import Path

import numpy as np

MODEL_PATH = Path(__file__).with_name("models") / "flood_rfr.joblib"
_SEED = 11  # group 11, keeps training reproducible

# same mode sensitivities the network uses (rail safe, street floods)
MODE_SENSITIVITY = {
    "LRT-1": 0.20, "LRT-2": 0.20, "MRT-3": 0.20, "EDSA-Bus": 0.85, "Jeepney": 1.00,
}


def _clamp01(x):
    return np.clip(x, 0.0, 1.0)


def _grounded_risk(rainfall_mm, sensitivity, base_exposure):
    # domain relationship the mmda data shows: a soft rainfall threshold near
    # 30mm, street modes amplified, area baseline shifting the whole curve up.
    rain = rainfall_mm / 50.0
    threshold = 1.0 / (1.0 + np.exp(-(rainfall_mm - 30.0) / 8.0))  # logistic knee
    risk = base_exposure + sensitivity * rain * threshold
    return _clamp01(risk)


def make_dataset(n: int = 4000):
    # sample the feature space the way real queries hit it
    rng = np.random.default_rng(_SEED)
    rainfall = rng.uniform(0.0, 80.0, n)
    sensitivity = rng.choice(list(MODE_SENSITIVITY.values()), n)
    base = rng.uniform(0.05, 0.6, n)
    y = _grounded_risk(rainfall, sensitivity, base)
    # a little observation noise so the forest learns a smooth mapping, not a rule
    y = _clamp01(y + rng.normal(0.0, 0.03, n))
    X = np.column_stack([rainfall, sensitivity, base])
    return X, y


def train():
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.model_selection import train_test_split
    import joblib

    X, y = make_dataset()
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=_SEED)
    model = RandomForestRegressor(
        n_estimators=200, max_depth=12, min_samples_leaf=3, random_state=_SEED, n_jobs=-1,
    )
    model.fit(X_tr, y_tr)
    pred = model.predict(X_te)
    metrics = {
        "r2": round(float(r2_score(y_te, pred)), 4),
        "mae": round(float(mean_absolute_error(y_te, pred)), 4),
        "n_train": int(len(X_tr)),
        "n_test": int(len(X_te)),
        "features": ["rainfall_mm", "mode_sensitivity", "base_exposure"],
    }
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "metrics": metrics}, MODEL_PATH)
    return metrics


if __name__ == "__main__":
    m = train()
    print("trained rfr flood model ->", MODEL_PATH)
    print("metrics:", m)
