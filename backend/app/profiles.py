# ahp commuter profiles.
# each profile is a weight set (wT, wF, wR, wP) over the four secondary criteria:
#   T = ridership, F = fare, R = flood risk, P = transfer friction.
# the weights come from the saaty 1-9 survey pipeline (normalized column
# average, respondents with cr >= 0.10 rejected) via ml/derive_ahp_weights.py,
# loaded from ml/models/ahp_weights.json. the json says whether it was built
# from SIMULATED respondents (mock) or the real survey export. if the file is
# missing entirely we fall back to the pinned 0.55/0.15 placeholder split.
import json
from dataclasses import dataclass
from pathlib import Path

_AHP_PATH = Path(__file__).parent / "ml" / "models" / "ahp_weights.json"


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    theme: str          # color theme on the frontend: blue / yellow / red / green
    priority: str       # the dominant criterion: T / F / R / P
    tagline: str
    w_T: float          # ridership weight
    w_F: float          # fare weight
    w_R: float          # flood-risk weight
    w_P: float          # transfer-friction weight
    cr: float | None = None          # mean consistency ratio of accepted respondents
    weights_source: str = "placeholder (0.55/0.15 split)"

    @property
    def weights(self) -> dict[str, float]:
        return {"T": self.w_T, "F": self.w_F, "R": self.w_R, "P": self.w_P}


_META = {
    "uncrowded":  ("Uncrowded", "blue", "T", "Prioritizes ridership"),
    "cheapest":   ("Cheapest", "yellow", "F", "Prioritizes fare"),
    "safest":     ("Safest", "red", "R", "Prioritizes flood risk"),
    "convenient": ("Convenient", "green", "P", "Prioritizes transfer friction"),
}

# placeholder fallback: main criterion 0.55, the other three 0.15 each
_DOM = 0.55
_OTH = 0.15


def _load_ahp() -> dict | None:
    try:
        return json.loads(_AHP_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _build_profiles() -> dict[str, Profile]:
    ahp = _load_ahp()
    out: dict[str, Profile] = {}
    for pid, (name, theme, priority, tagline) in _META.items():
        loaded = False
        if ahp and pid in ahp.get("profiles", {}):
            # a partial or malformed weights file must never keep the whole api
            # from starting: validate hard, fall back to the placeholder split
            try:
                p = ahp["profiles"][pid]
                raw = p["weights"]
                vals = [float(raw[c]) for c in ("T", "F", "R", "P")]
                total = sum(vals)
                if not all(v >= 0.0 and v == v and v != float("inf") for v in vals) or total <= 0:
                    raise ValueError(f"bad weight values for {pid}: {raw}")
                # renormalize so the four rounded json values sum to exactly 1,
                # keeping the paper's 2.0 penalty bound airtight
                w = {c: v / total for c, v in zip(("T", "F", "R", "P"), vals)}
                src = "ahp survey pipeline"
                if "SIMULATED" in ahp.get("source", "").upper():
                    src = "ahp pipeline on SIMULATED respondents (mock)"
                out[pid] = Profile(
                    id=pid, name=name, theme=theme, priority=priority, tagline=tagline,
                    w_T=w["T"], w_F=w["F"], w_R=w["R"], w_P=w["P"],
                    cr=p.get("mean_cr_accepted"), weights_source=src,
                )
                loaded = True
            except Exception:
                loaded = False  # fall through to the placeholder below
        if not loaded:
            w = {c: (_DOM if c == priority else _OTH) for c in ("T", "F", "R", "P")}
            out[pid] = Profile(
                id=pid, name=name, theme=theme, priority=priority, tagline=tagline,
                w_T=w["T"], w_F=w["F"], w_R=w["R"], w_P=w["P"],
            )
    return out


PROFILES: dict[str, Profile] = _build_profiles()

# baseline = plain distance based a*, zero weights. this is what the
# framework gets compared against in the benchmark and /compare
BASELINE = Profile(
    id="baseline", name="Baseline", theme="gray", priority="-",
    tagline="distance-based A*", w_T=0.0, w_F=0.0, w_R=0.0, w_P=0.0,
)

# the frontend stores the display title ("Safest") and also matches loosely on
# lowercased bits like "safe", "cheap", "fewer", so handle those too.
_ALIASES = {
    "safe": "safest",
    "cheap": "cheapest",
    "fewer": "convenient",
    "transfer": "convenient",
}


def resolve_profile(value: str) -> Profile:
    # find a profile from an id, display name, or one of the loose aliases.
    # aliases match whole words only - a substring match let junk like
    # 'unsafe-x' resolve to safest instead of getting a clean 422
    if not value:
        raise KeyError("empty profile")
    key = value.strip().lower()
    if key == "baseline":
        return BASELINE
    if key in PROFILES:
        return PROFILES[key]
    words = set(key.replace("-", " ").split())
    for fragment, profile_id in _ALIASES.items():
        if fragment in words:
            return PROFILES[profile_id]
    raise KeyError(f"unknown profile: {value!r}")
