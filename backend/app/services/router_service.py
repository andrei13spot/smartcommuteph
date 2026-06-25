# puts it together: profile + origin/destination + context -> a* route -> response.
# ties the graph, the cost context (predictors + normalization), the a* search,
# and the bits the result screen needs.
from __future__ import annotations

from datetime import datetime

from ..ml.flood import fetch_pagasa_rainfall_mm
from ..profiles import Profile, resolve_profile
from ..routing.astar import shortest_route
from ..routing.cost import CostContext, transfer_friction
from ..routing.graph import Edge, Graph, load_graph
from ..schemas import (
    AnchorOut,
    CriterionOut,
    ProfileOut,
    RouteResponse,
    RouteSummary,
    SegmentOut,
)


def _anchor_out(graph: Graph, node_id: str) -> AnchorOut:
    n = graph.node(node_id)
    return AnchorOut(id=n.id, name=n.name, area=n.area, lat=n.lat, lng=n.lng, lines=list(n.lines))


def _profile_out(p: Profile) -> ProfileOut:
    return ProfileOut(
        id=p.id, name=p.name, theme=p.theme, priority=p.priority,
        tagline=p.tagline, weights=p.weights,
    )


def _level(value: float) -> str:
    if value < 0.34:
        return "Low"
    if value < 0.67:
        return "Moderate"
    return "High"


def _crowd_word(value: float) -> str:
    return {"Low": "Light", "Moderate": "Moderate", "High": "Heavy"}[_level(value)]


def _modes_in_order(edges: list[Edge]) -> list[str]:
    modes: list[str] = []
    for e in edges:
        if not modes or modes[-1] != e.mode:
            modes.append(e.mode)
    return modes


def _count_transfers(edges: list[Edge]) -> int:
    return max(0, len(_modes_in_order(edges)) - 1)


def _route_criteria(ctx: CostContext, edges: list[Edge]) -> dict[str, CriterionOut]:
    # roll the per-edge criteria up to a route-level value
    if not edges:
        zero = CriterionOut(value=0.0, level="Low")
        return {"T": zero, "F": zero, "R": zero, "P": zero}

    t = sum(ctx.criteria[e.id].T for e in edges) / len(edges)
    f = sum(ctx.criteria[e.id].F for e in edges) / len(edges)
    r = max(ctx.criteria[e.id].R for e in edges)  # worst segment for flood
    # transfer friction along the path, per leg
    prev_mode: str | None = None
    p_vals: list[float] = []
    for e in edges:
        p_vals.append(ctx.friction_norm(prev_mode, e.mode))
        prev_mode = e.mode
    p = sum(p_vals) / len(p_vals)

    return {
        "T": CriterionOut(value=round(t, 2), level=_level(t)),
        "F": CriterionOut(value=round(f, 2), level=_level(f)),
        "R": CriterionOut(value=round(r, 2), level=_level(r)),
        "P": CriterionOut(value=round(p, 2), level=_level(p)),
    }


def _segments(graph: Graph, edges: list[Edge]) -> list[SegmentOut]:
    out: list[SegmentOut] = []
    prev_mode: str | None = None
    for e in edges:
        out.append(SegmentOut(
            from_id=e.src, from_name=graph.node(e.src).name,
            to_id=e.dst, to_name=graph.node(e.dst).name,
            mode=e.mode, time_min=e.base_time, fare_php=e.fare,
            is_transfer=(prev_mode is not None and prev_mode != e.mode),
        ))
        prev_mode = e.mode
    return out


def _prioritized(profile: Profile, summary: RouteSummary,
                 criteria: dict[str, CriterionOut]) -> dict[str, str]:
    # headline value + subtitle for whatever the profile cares about most
    if profile.priority == "T":
        return {"title": _crowd_word(criteria["T"].value), "subtitle": "Crowd level"}
    if profile.priority == "F":
        return {"title": f"₱{int(round(summary.fare_php))}", "subtitle": "Lowest total fare"}
    if profile.priority == "R":
        return {"title": criteria["R"].level, "subtitle": "Flood risk"}
    return {"title": str(summary.transfers), "subtitle": "Vehicle changes"}


def _why(profile: Profile, summary: RouteSummary, criteria: dict[str, CriterionOut]) -> dict[str, str]:
    # short reason text shown on the result card
    modes = " then ".join(summary.modes) or "a single ride"
    if profile.priority == "T":
        return {
            "heading": "Avoids the most crowded stations",
            "description": "this route sticks to segments forecast to be below peak load, "
                           f"so crowding stays {_crowd_word(criteria['T'].value).lower()} for your time.",
        }
    if profile.priority == "F":
        return {
            "heading": "Bypasses the most expensive rides",
            "description": f"this path uses cheaper segments ({modes}) to bring the total "
                           f"down to about ₱{int(round(summary.fare_php))}.",
        }
    if profile.priority == "R":
        return {
            "heading": "Avoids flood-prone streets",
            "description": "this path keeps to the lowest-exposure segments available, "
                           f"holding flood risk in the {criteria['R'].level.lower()} range for the rainfall.",
        }
    return {
        "heading": "Minimizes vehicle changes",
        "description": f"this route makes {summary.transfers} transfer(s), "
                       "cutting the time spent walking and waiting between modes.",
    }


def build_route(req_origin: str, req_destination: str, req_profile: str,
                hour: int | None, rainfall_mm: float | None) -> RouteResponse:
    graph = load_graph()
    profile = resolve_profile(req_profile)
    h = hour if hour is not None else datetime.now().hour
    rain = rainfall_mm if rainfall_mm is not None else fetch_pagasa_rainfall_mm()

    ctx = CostContext(graph, hour=h, rainfall_mm=rain)
    result = shortest_route(graph, req_origin, req_destination, profile, ctx)

    edges = result.edges
    # total time = in-vehicle time + the transfer friction we actually paid
    transfer_minutes = 0.0
    prev_mode: str | None = None
    for e in edges:
        transfer_minutes += transfer_friction(prev_mode, e.mode)
        prev_mode = e.mode
    summary = RouteSummary(
        time_min=round(sum(e.base_time for e in edges) + transfer_minutes, 1),
        distance_km=round(sum(e.distance_km for e in edges), 1),
        fare_php=round(sum(e.fare for e in edges), 1),
        transfers=_count_transfers(edges),
        modes=_modes_in_order(edges),
    )
    criteria = _route_criteria(ctx, edges)

    return RouteResponse(
        origin=_anchor_out(graph, req_origin),
        destination=_anchor_out(graph, req_destination),
        profile=_profile_out(profile),
        found=result.found,
        summary=summary,
        criteria=criteria,
        prioritized=_prioritized(profile, summary, criteria),
        why=_why(profile, summary, criteria),
        segments=_segments(graph, edges),
        expanded_nodes=result.expanded_nodes,
    )
