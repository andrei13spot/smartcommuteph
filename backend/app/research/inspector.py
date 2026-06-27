# query inspector: run one od + profile and return the path with a per-edge
# cost decomposition, so the dashboard can show how each criterion contributes.
from __future__ import annotations

import time

from ..profiles import resolve_profile
from ..routing.astar import shortest_route
from ..routing.cost import CostContext
from ..routing.graph import load_graph
from .benchmark import BASELINE


def inspect(origin: str, destination: str, profile_name: str,
            hour: int = 8, rainfall_mm: float = 30.0) -> dict:
    graph = load_graph()
    profile = resolve_profile(profile_name)
    ctx = CostContext(graph, hour=hour, rainfall_mm=rainfall_mm)
    t0 = time.perf_counter()
    res = shortest_route(graph, origin, destination, profile, ctx)
    query_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    # distance-based baseline over the same od, for the "vs baseline" counters
    base = shortest_route(graph, origin, destination, BASELINE, ctx)

    rows = []
    prev_mode = None
    for e in res.edges:
        c = ctx.criteria[e.id]
        p = ctx.friction_norm(prev_mode, e.mode)
        mult = 1.0 + profile.w_T * c.T + profile.w_F * c.F + profile.w_R * c.R + profile.w_P * p
        rows.append({
            "from_id": e.src, "to_id": e.dst,
            "from": graph.node(e.src).name,
            "to": graph.node(e.dst).name,
            "mode": e.mode,
            "base_time": round(e.base_time, 2),
            "T": round(c.T, 2), "F": round(c.F, 2), "R": round(c.R, 2), "P": round(p, 2),
            "multiplier": round(mult, 3),
            "cost": round(e.base_time * mult, 2),
        })
        prev_mode = e.mode

    # ordered path node ids: first leg's origin, then each leg's destination
    path = ([res.edges[0].src] + [e.dst for e in res.edges]) if res.edges else [origin]

    return {
        "origin": graph.node(origin).name,
        "destination": graph.node(destination).name,
        "origin_id": origin,
        "destination_id": destination,
        "profile": {
            "id": profile.id, "name": profile.name,
            "weights": profile.weights, "priority": profile.priority,
        },
        "found": res.found,
        "expanded_nodes": res.expanded_nodes,
        "baseline_nodes": base.expanded_nodes,
        "query_ms": query_ms,
        "total_cost": round(res.total_cost, 2),
        "path": path,
        "expanded_order": res.expanded_order,
        "decomposition": rows,
    }
