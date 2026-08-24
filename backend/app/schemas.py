# request and response models for the routing api
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

_PASSENGER_TYPES = {"regular", "student", "senior"}


def _clean_passenger_type(v: str | None) -> str | None:
    # 'Student', ' SENIOR ' etc. must not silently lose the discount
    if v is None:
        return None
    cleaned = v.strip().lower()
    if not cleaned:
        return None
    if cleaned not in _PASSENGER_TYPES:
        raise ValueError(f"passenger_type must be one of {sorted(_PASSENGER_TYPES)}")
    return cleaned


# ----- requests -----
class RouteRequest(BaseModel):
    origin: str = Field(..., description="origin anchor id, e.g. 'cubao'")
    destination: str = Field(..., description="destination anchor id, e.g. 'pasay'")
    profile: str = Field(..., description="profile id, name, or alias, e.g. 'safest'")
    hour: int | None = Field(
        None, ge=0, le=23,
        description="departure hour 0-23 for ridership; defaults to server time",
    )
    rainfall_mm: float | None = Field(
        None, ge=0, le=500, allow_inf_nan=False,
        description="rainfall override in mm (0-500); defaults to the live value",
    )
    passenger_type: str | None = Field(
        None,
        description="regular | student | senior; student/senior gets 20% fare discount",
    )

    _pt = field_validator("passenger_type")(_clean_passenger_type)


class CompareRequest(BaseModel):
    origin: str
    destination: str
    hour: int | None = Field(None, ge=0, le=23)
    rainfall_mm: float | None = Field(None, ge=0, le=500, allow_inf_nan=False)
    passenger_type: str | None = Field(None, description="regular | student | senior")

    _pt = field_validator("passenger_type")(_clean_passenger_type)


# ----- response pieces -----
class AnchorOut(BaseModel):
    id: str
    name: str
    area: str
    lat: float
    lng: float
    lines: list[str]


class ProfileOut(BaseModel):
    id: str
    name: str
    theme: str
    priority: str
    tagline: str
    weights: dict[str, float]
    cr: float | None = None            # mean consistency ratio of accepted respondents
    weights_source: str | None = None  # ahp pipeline vs placeholder, mock vs real


class CriterionOut(BaseModel):
    value: float = Field(..., description="normalized route value 0..1")
    level: str = Field(..., description="low / moderate / high")


class SegmentOut(BaseModel):
    from_id: str
    from_name: str
    to_id: str
    to_name: str
    mode: str
    time_min: float
    fare_php: float
    is_transfer: bool = Field(..., description="true if this leg boards a new mode")


class RouteSummary(BaseModel):
    time_min: float
    distance_km: float
    fare_php: float
    fare_discounted_php: float | None = Field(
        None, description="fare after 20% discount, set when student/senior"
    )
    transfers: int
    modes: list[str]


class RouteResponse(BaseModel):
    origin: AnchorOut
    destination: AnchorOut
    profile: ProfileOut
    found: bool
    summary: RouteSummary
    criteria: dict[str, CriterionOut] = Field(
        ..., description="route-level T'/F'/R'/P' after normalization"
    )
    prioritized: dict[str, str] = Field(
        ..., description="headline value + subtitle for the profile's main criterion"
    )
    why: dict[str, str] = Field(..., description="heading + description")
    segments: list[SegmentOut]
    expanded_nodes: int = Field(..., description="a* states expanded (rq3 metric)")
    exec_ms: float = Field(0.0, description="how long the a* query took")


class CompareResponse(BaseModel):
    origin: AnchorOut
    destination: AnchorOut
    routes: list[RouteResponse]


class NetworkEdgeOut(BaseModel):
    from_id: str
    to_id: str
    mode: str


class NetworkResponse(BaseModel):
    # whole graph for the overview map
    nodes: list[AnchorOut]
    edges: list[NetworkEdgeOut]
