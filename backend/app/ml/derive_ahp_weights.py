# derives the four ahp profile weight vectors (the decision layer).
# method is exactly the paper's: each respondent gives a 4x4 pairwise
# comparison matrix on the saaty 1-9 scale, weights come from the normalized
# column average, respondents with consistency ratio cr >= 0.10 are rejected,
# and the accepted vectors are averaged per profile.
#
# IMPORTANT: until the real 150-respondent survey export arrives, the input
# matrices are SIMULATED (see simulate_respondents). the output json is loudly
# labeled as mock. when princess hands over the real survey matrices, replace
# the simulate_respondents call in main with a loader for her export and rerun
# this script - derive() itself does not change.
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

OUT_PATH = Path(__file__).with_name("models") / "ahp_weights.json"
_SEED = 11  # group 11, reproducible

# criteria order everywhere: T (ridership), F (fare), R (flood), P (transfer)
CRITERIA = ["T", "F", "R", "P"]
N = 4
RI_N4 = 0.89  # random index for n=4, matching the value the paper uses

# which criterion each profile prioritizes
PROFILE_PRIORITY = {
    "uncrowded": "T",
    "cheapest": "F",
    "safest": "R",
    "convenient": "P",
}


def weights_normalized_column_average(matrix: np.ndarray) -> np.ndarray:
    # the paper's method: normalize each column by its sum, then average rows
    col_sums = matrix.sum(axis=0)
    normalized = matrix / col_sums
    w = normalized.mean(axis=1)
    return w / w.sum()


def consistency_ratio(matrix: np.ndarray, w: np.ndarray) -> float:
    # lambda_max from the weighted-sum ratio, then ci/ri
    lam = float(np.mean((matrix @ w) / w))
    ci = (lam - N) / (N - 1)
    return ci / RI_N4


def derive(matrices: list[np.ndarray]) -> dict:
    # run every respondent matrix through the paper's pipeline for one profile
    accepted, crs = [], []
    for m in matrices:
        w = weights_normalized_column_average(m)
        cr = consistency_ratio(m, w)
        crs.append(cr)
        if cr < 0.10:
            accepted.append(w)
    if not accepted:
        raise SystemExit(
            "every respondent failed the cr < 0.10 filter - check the input "
            "matrices before deriving weights")
    mean_w = np.mean(accepted, axis=0)
    mean_w = mean_w / mean_w.sum()
    accepted_crs = [c for c in crs if c < 0.10]
    return {
        "weights": {c: round(float(v), 4) for c, v in zip(CRITERIA, mean_w)},
        "n_respondents": len(matrices),
        "n_accepted": len(accepted),
        "n_rejected_cr": len(matrices) - len(accepted),
        "mean_cr_accepted": round(float(np.mean(accepted_crs)), 4),
    }


def _saaty_snap(x: float) -> float:
    # snap a continuous preference to the closest saaty value (1..9 or its
    # reciprocal), since respondents answer on the discrete 1-9 scale
    scale = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9], dtype=float)
    if x >= 1.0:
        return float(scale[np.argmin(np.abs(scale - x))])
    return 1.0 / float(scale[np.argmin(np.abs(scale - 1.0 / x))])


def simulate_respondents(priority: str, n_resp: int, rng: np.random.Generator) -> list[np.ndarray]:
    # MOCK DATA: synthetic survey respondents for one profile. each respondent
    # prefers the profile's dominant criterion (saaty ~3-6 over the others)
    # with person-to-person noise, and some are sloppy enough to fail the cr
    # check - matching what a real saaty survey batch looks like.
    dom = CRITERIA.index(priority)
    out = []
    for _ in range(n_resp):
        dom_strength = rng.uniform(2.5, 6.0)   # how much this person favors the dominant criterion
        sloppiness = rng.uniform(0.0, 0.45)    # noise that drives inconsistency
        m = np.ones((N, N))
        for i in range(N):
            for j in range(i + 1, N):
                if i == dom:
                    base = dom_strength
                elif j == dom:
                    base = 1.0 / dom_strength
                else:
                    base = rng.uniform(0.5, 2.0)  # non-dominant pairs near-equal
                noisy = base * float(np.exp(rng.normal(0.0, sloppiness)))
                v = _saaty_snap(noisy)
                m[i, j] = v
                m[j, i] = 1.0 / v
        out.append(m)
    return out


def main() -> None:
    rng = np.random.default_rng(_SEED)
    profiles = {}
    for pid, priority in PROFILE_PRIORITY.items():
        matrices = simulate_respondents(priority, 150, rng)
        profiles[pid] = {"priority": priority, **derive(matrices)}

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "description": "ahp profile weight vectors via normalized column average, "
                       "cr >= 0.10 rejected (saaty n=4, ri 0.90).",
        "source": "SIMULATED respondents (mock) - NOT the real survey. replace "
                  "simulate_respondents with the real 150-respondent export and "
                  "rerun derive_ahp_weights.py before the defense claims survey data.",
        "profiles": profiles,
    }, indent=2), encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    for pid, p in profiles.items():
        print(f"  {pid:10} {p['weights']}  accepted {p['n_accepted']}/{p['n_respondents']}  mean cr {p['mean_cr_accepted']}")


if __name__ == "__main__":
    main()
