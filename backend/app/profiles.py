# ahp commuter profiles.
# each profile is a weight set (wT, wF, wR, wP) over the four secondary criteria:
#   T = ridership, F = fare, R = flood risk, P = transfer friction.
# normally these come from the saaty 1-9 survey (kept under CR < 0.10). here we
# pin the four published profiles: the main criterion gets 0.55, the other three
# split the rest (0.15 each), so each set sums to 1.
from dataclasses import dataclass


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

    @property
    def weights(self) -> dict[str, float]:
        return {"T": self.w_T, "F": self.w_F, "R": self.w_R, "P": self.w_P}


# main criterion 0.55, the other three 0.15 each (sums to 1)
_DOM = 0.55
_OTH = 0.15

PROFILES: dict[str, Profile] = {
    "uncrowded": Profile(
        id="uncrowded", name="Uncrowded", theme="blue", priority="T",
        tagline="Prioritizes ridership",
        w_T=_DOM, w_F=_OTH, w_R=_OTH, w_P=_OTH,
    ),
    "cheapest": Profile(
        id="cheapest", name="Cheapest", theme="yellow", priority="F",
        tagline="Prioritizes fare",
        w_T=_OTH, w_F=_DOM, w_R=_OTH, w_P=_OTH,
    ),
    "safest": Profile(
        id="safest", name="Safest", theme="red", priority="R",
        tagline="Prioritizes flood risk",
        w_T=_OTH, w_F=_OTH, w_R=_DOM, w_P=_OTH,
    ),
    "convenient": Profile(
        id="convenient", name="Convenient", theme="green", priority="P",
        tagline="Prioritizes transfer friction",
        w_T=_OTH, w_F=_OTH, w_R=_OTH, w_P=_DOM,
    ),
}

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
    # find a profile from an id, display name, or one of the loose aliases
    if not value:
        raise KeyError("empty profile")
    key = value.strip().lower()
    if key == "baseline":
        return BASELINE
    if key in PROFILES:
        return PROFILES[key]
    for fragment, profile_id in _ALIASES.items():
        if fragment in key:
            return PROFILES[profile_id]
    raise KeyError(f"unknown profile: {value!r}")
