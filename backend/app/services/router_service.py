# puts it together: profile + origin/destination + context -> a* route -> response.
# ties the graph, the cost context (predictors + normalization), the a* search,
# and the bits the result screen needs.
from __future__ import annotations

import time
from datetime import datetime

from ..ml.flood import fetch_rainfall_mm
from ..profiles import Profile, resolve_profile
from ..routing.astar import shortest_route
from ..routing.cost import CostContext, count_transfers, modes_in_order, next_mode_state, path_transfer_friction
from ..routing.fares import path_fare
from ..routing.graph import Edge, Graph, load_graph
from ..schemas import (
    AnchorOut,
    CriterionOut,
    ProfileOut,
    RouteResponse,
    RouteSummary,
    SegmentOut,
)


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


# flood level shown to the commuter: how much the rain raises the route's
# flood risk above its dry-day value, averaged along the route. the dry value
# is the road's flood history (mmda exposure); a road with a flooding past is
# not flooding today when it is not raining. averaging (not the worst segment)
# keeps the forest's small wobble on single segments from reading as rain.
# thresholds from the benchmark routes: 8 mm adds about 0.004, 30 mm about
# 0.10, 45 mm about 0.23.
_FLOOD_LOW, _FLOOD_HIGH = 0.03, 0.15
def _crowd_level(value: float) -> str:
    # one crowding scale for every crowd label in the app: light / medium / high
    return {"Low": "Light", "Moderate": "Medium", "High": "High"}[_level(value)]


def _flood_level(value: float) -> str:
    if value < _FLOOD_LOW:
        return "Low"
    if value < _FLOOD_HIGH:
        return "Moderate"
    return "High"


def _route_criteria(ctx: CostContext, edges: list[Edge]) -> dict[str, CriterionOut]:
    # roll the per-edge criteria up to a route-level value
    if not edges:
        zero = CriterionOut(value=0.0, level="Low")
        return {"T": zero, "F": zero, "R": zero, "P": zero}

    # crowd level: the predicted crowding itself (0-1) averaged over the rides,
    # not the per-query 0-1 scaling, which cancels the hour out (a route read
    # "high" at noon and "moderate" at 3 am). walks have no crowding to count
    rides = [e for e in edges if e.mode != "Walk"] or edges
    t = sum(ctx.raw_crowd[e.id] for e in rides) / len(rides)
    prev_f: str | None = None
    f_vals = []
    for e in edges:
        f_vals.append(ctx.fare_norm(e, prev_f))
        prev_f = next_mode_state(prev_f, e.mode)
    f = sum(f_vals) / len(f_vals)
    # flood: the rain-driven part of the raw risk, averaged along the route. the old
    # value was the worst min-max scaled segment, which puts the riskiest edge
    # of the network at 1 on every query, so every route read "high"
    r = sum(ctx.rain_flood[e.id] for e in edges) / len(edges)
    # transfer friction along the path, averaged over the transitions where a
    # transfer can actually happen (real stops), not every 300m virtual hop -
    # dividing by the edge count made a worse transfer look lower on long routes
    prev_mode: str | None = None
    p_vals: list[float] = []
    for e in edges:
        if e.mode != "Walk" and (not ctx.graph.nodes[e.src].virtual or prev_mode != e.mode):
            p_vals.append(ctx.friction_norm(prev_mode, e.mode, e.src))
        prev_mode = next_mode_state(prev_mode, e.mode)
    p = sum(p_vals) / len(p_vals) if p_vals else 0.0

    return {
        "T": CriterionOut(value=round(t, 2), level=_crowd_level(t)),
        "F": CriterionOut(value=round(f, 2), level=_level(f)),
        "R": CriterionOut(value=round(r, 2), level=_flood_level(r)),
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


def _shown_fare(summary: RouteSummary) -> float:
    # the fare the rider pays: the student / senior fare when one was asked
    # for, the same number the fare tiles show (the headline used to show the
    # regular fare next to a student fare tile, php 80 vs 64 on the same route)
    return summary.fare_discounted_php if summary.fare_discounted_php is not None else summary.fare_php


def _prioritized(profile: Profile, summary: RouteSummary,
                 criteria: dict[str, CriterionOut]) -> dict[str, str]:
    # headline value + subtitle for whatever the profile cares about most
    if profile.priority == "T":
        # one crowding scale everywhere: light / medium / high, same as the tiles
        return {"title": criteria["T"].level, "subtitle": "Crowd level"}
    if profile.priority == "F":
        return {"title": f"₱{int(round(_shown_fare(summary)))}", "subtitle": "Lowest total fare"}
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
                           f"so crowding stays {criteria['T'].level.lower()} for your time.",
        }
    if profile.priority == "F":
        return {
            "heading": "Bypasses the most expensive rides",
            "description": f"this path uses cheaper segments ({modes}) to bring the total "
                           f"down to about ₱{int(round(_shown_fare(summary)))}.",
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


from functools import lru_cache


@lru_cache(maxsize=16)
def _shared_ctx(hour: int, rainfall_mm: float) -> CostContext:
    # one context per (hour, rainfall): /compare calls build_route five times
    # for the same query and was paying the full ml inference each time
    return CostContext(load_graph(), hour=hour, rainfall_mm=rainfall_mm)


def build_route(req_origin: str, req_destination: str, req_profile: str,
                hour: int | None, rainfall_mm: float | None,
                passenger_type: str | None = None) -> RouteResponse:
    graph = load_graph()
    profile = resolve_profile(req_profile)
    h = hour if hour is not None else datetime.now().hour
    rain = rainfall_mm if rainfall_mm is not None else fetch_rainfall_mm()

    ctx = _shared_ctx(h, round(rain, 1))
    # time the actual a* run, this is kpi #8
    t0 = time.perf_counter()
    result = shortest_route(graph, req_origin, req_destination, profile, ctx)
    exec_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    edges = result.edges
    # total time = in-vehicle time + the transfer friction we actually paid
    transfer_minutes = path_transfer_friction(ctx.graph, edges)
    fare = round(path_fare(graph, edges), 1)
    # student or senior: official discounted matrix where published, else 20% off
    discounted = round(path_fare(graph, edges, discounted=True), 1) if passenger_type in ("student", "senior") else None
    # the same trip paying the rail legs with a beep card (lrt-1 and lrt-2 stored value matrices)
    card = round(path_fare(graph, edges, card=True), 1)
    summary = RouteSummary(
        time_min=round(sum(e.base_time for e in edges) + transfer_minutes, 1),
        distance_km=round(sum(e.distance_km for e in edges), 1),
        fare_php=fare,
        fare_discounted_php=discounted,
        fare_card_php=card,
        transfers=count_transfers(edges),
        modes=modes_in_order(edges),
    )
    criteria = _route_criteria(ctx, edges)

    return RouteResponse(
        origin=AnchorOut.from_node(graph.node(req_origin)),
        destination=AnchorOut.from_node(graph.node(req_destination)),
        profile=_profile_out(profile),
        found=result.found,
        summary=summary,
        criteria=criteria,
        prioritized=_prioritized(profile, summary, criteria),
        why=_why(profile, summary, criteria),
        segments=_segments(graph, edges),
        expanded_nodes=result.expanded_nodes,
        exec_ms=exec_ms,
    )
