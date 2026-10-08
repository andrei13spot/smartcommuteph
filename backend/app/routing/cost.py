# multi-criteria edge cost.
# cost(e) = time(e) * (1 + wT*T' + wF*F' + wR*R' + wP*P')
# T', F', R', P' are min-max normalized to 0..1 (ridership, fare, flood, transfer).
# the transfer term depends on the arriving mode, so cost is figured out per state
# while a* expands, not baked into the edge.
from __future__ import annotations

from dataclasses import dataclass

from ..ml import flood, ridership
from ..profiles import Profile
from .graph import Edge, Graph

# transfer friction adjacency matrix (table 3 in the paper). raw penalty for
# switching from mode i to mode j. same mode is 0 except jeepney->jeepney = 0.5
# (changing jeepney lines still costs waiting and re-paying).
_FRICTION_MATRIX = {
    "LRT-1":    {"LRT-1": 0.0, "LRT-2": 1.5, "MRT-3": 1.7, "EDSA-Bus": 1.3, "Jeepney": 2.0},
    "LRT-2":    {"LRT-1": 1.5, "LRT-2": 0.0, "MRT-3": 1.4, "EDSA-Bus": 1.2, "Jeepney": 1.9},
    "MRT-3":    {"LRT-1": 1.7, "LRT-2": 1.4, "MRT-3": 0.0, "EDSA-Bus": 1.0, "Jeepney": 1.8},
    "EDSA-Bus": {"LRT-1": 1.3, "LRT-2": 1.2, "MRT-3": 1.0, "EDSA-Bus": 0.0, "Jeepney": 1.6},
    "Jeepney":  {"LRT-1": 2.0, "LRT-2": 1.9, "MRT-3": 1.8, "EDSA-Bus": 1.6, "Jeepney": 0.5},
}
# walking between vehicles carries no friction of its own. the search state
# remembers which vehicle was left before the walk ("Walk<MRT-3>"), and the
# next vehicle boarded pays table 3 from that vehicle, exactly as a direct
# transfer would: jeepney -> walk -> jeepney pays the 0.5 line change on the
# second jeepney, mrt -> walk -> jeepney pays 1.8, and a trip that starts by
# walking to its first jeepney pays nothing. charging it on the walk edge made
# the penalty scale with walking time (equation 4 multiplies by edge time).
def next_mode_state(arriving: str | None, edge_mode: str) -> str:
    if edge_mode == "Walk":
        return f"Walk<{vehicle_of(arriving) or ''}>"
    return edge_mode


def vehicle_of(mode_state: str | None) -> str | None:
    if mode_state and mode_state.startswith("Walk<"):
        return mode_state[5:-1] or None
    return mode_state


# biggest entry, used to normalize P' into 0..1
_MAX_FRICTION = max(v for row in _FRICTION_MATRIX.values() for v in row.values())


def _mode_runs(edges: list[Edge]) -> list[str]:
    runs: list[str] = []
    for e in edges:
        if not runs or runs[-1] != e.mode:
            runs.append(e.mode)
    return runs


def modes_in_order(edges: list[Edge]) -> list[str]:
    # the sequence of modes ridden, collapsing consecutive legs of the same
    # mode. walking between lines is not a mode the rider takes
    modes: list[str] = []
    for m in _mode_runs(edges):
        if m != "Walk" and (not modes or modes[-1] != m):
            modes.append(m)
    return modes


def count_transfers(edges: list[Edge]) -> int:
    # vehicles boarded minus one; a walk between two jeepney lines is a change
    # of jeepney, so the two rides count separately
    rides = [m for m in _mode_runs(edges) if m != "Walk"]
    return max(0, len(rides) - 1)


def transfer_friction(mode_a: str | None, mode_b: str, continuing: bool = False) -> float:
    # raw friction of going from mode_a to mode_b.
    # mode_a is none on the first leg (no transfer yet).
    # continuing=True means the hop happens at a virtual stop mid-corridor:
    # staying on the same vehicle is not a transfer, so the same-mode diagonal
    # (jeepney->jeepney 0.5 = changing jeepney LINES) must not be charged there.
    if mode_b == "Walk":
        return 0.0  # walking pays nothing; the next vehicle pays the transfer
    if mode_a is not None and mode_a.startswith("Walk<"):
        mode_a, continuing = vehicle_of(mode_a), False  # a walk always means a new vehicle
    if mode_a is None:
        return 0.0
    if continuing and mode_a == mode_b:
        return 0.0
    row = _FRICTION_MATRIX.get(mode_a)
    if not row:
        return 0.0
    return float(row.get(mode_b, 0.0))


def path_transfer_friction(graph: Graph, edges: list[Edge]) -> float:
    # raw table-3 friction actually paid along a path; riding through a
    # virtual stop is not a transfer
    total = 0.0
    prev: str | None = None
    for e in edges:
        total += transfer_friction(prev, e.mode, continuing=graph.nodes[e.src].virtual)
        prev = next_mode_state(prev, e.mode)
    return total


def _min_max_scaled(raw: dict[str, float]) -> dict[str, float]:
    # min-max normalize a dict of raw values into 0..1 (flat = all zeros)
    lo, hi = (min(raw.values()), max(raw.values())) if raw else (0.0, 0.0)
    return {k: (0.0 if hi <= lo else (v - lo) / (hi - lo)) for k, v in raw.items()}


@dataclass
class EdgeCriteria:
    # normalized criteria for one edge under a query (transfer is per-state, not here)
    T: float  # ridership
    F: float  # fare
    R: float  # flood risk


_DRY_FLOOD: dict[str, float] = {}


def dry_flood(graph: Graph) -> dict[str, float]:
    # the forest's flood value for every edge with no rain: the road's flood
    # history from the mmda exposure. computed once, the graph is cached
    if not _DRY_FLOOD:
        edges = list(graph.edges.values())
        vals = flood.predictor.predict_batch(edges, 0.0)
        _DRY_FLOOD.update(vals if isinstance(vals, dict) else dict(zip((e.id for e in edges), vals)))
    return _DRY_FLOOD


class CostContext:
    # one per query: run the predictors then min-max normalize ridership/fare/flood
    # across all edges
    def __init__(self, graph: Graph, hour: int, rainfall_mm: float):
        self.graph = graph
        self.hour = hour
        self.rainfall_mm = rainfall_mm

        from . import fares

        eids = list(graph.edges)
        edge_list = [graph.edges[eid] for eid in eids]
        # flood is predicted for all edges in one batched sklearn call: the
        # per-edge single-row predict was ~550 model calls per query (25s+)
        flood_vals = flood.predictor.predict_batch(edge_list, rainfall_mm)
        raw_T: dict[str, float] = {}
        raw_F: dict[str, float] = {}
        raw_R: dict[str, float] = {}
        for eid, edge, fv in zip(eids, edge_list, flood_vals):
            raw_T[eid] = ridership.predictor.predict(edge, hour)
            # per-km fare of the edge. the search itself uses fare_norm below,
            # which also adds the base fare when the edge boards a new vehicle
            raw_F[eid] = fares.marginal_fare(edge.mode, edge.distance_km)
            raw_R[eid] = fv

        # R' is the flood risk the rain adds today: the forest's value at this
        # rainfall minus its dry-day value (the road's flood history). with the
        # history left in, safest dodged old flood spots on a dry night and could
        # pick a pricier, riskier route; now a dry day leaves R' flat and safest
        # follows the fastest route, and in rain it avoids the roads the rain hits
        dry = dry_flood(graph)
        rain_R = {eid: max(0.0, v - dry.get(eid, 0.0)) for eid, v in raw_R.items()}
        T, F, R = (_min_max_scaled(r) for r in (raw_T, raw_F, rain_R))
        self.criteria: dict[str, EdgeCriteria] = {
            eid: EdgeCriteria(T=T[eid], F=F[eid], R=R[eid]) for eid in graph.edges
        }
        self.raw_flood = raw_R  # raw (un-normalized) flood values, read by the rainfall-effect test
        self.rain_flood = rain_R  # the rain-driven part, what R' scales
        self.raw_crowd = raw_T  # predicted crowding (0-1) before scaling, for the route's crowd level
        # scale for the boarding-aware fare term: the most any edge can add to
        # the trip (its mode's base fare plus its per-km part)
        self._fare_scale = max((fares.mode_params(e.mode)["base_php"] + fares.marginal_fare(e.mode, e.distance_km)
                                for e in edge_list if e.mode != "Walk"), default=1.0) or 1.0

    def friction_norm(self, arriving_mode: str | None, edge_mode: str,
                      src_id: str | None = None) -> float:
        # P' = normalized transfer friction. src_id is where the transition
        # happens: at a virtual stop the ride just continues (no transfer).
        continuing = bool(src_id) and self.graph.nodes[src_id].virtual
        return transfer_friction(arriving_mode, edge_mode, continuing) / _MAX_FRICTION

    def fare_norm(self, edge: Edge, arriving_mode: str | None) -> float:
        # F' = what this edge adds to the fare, scaled 0..1: boarding a new
        # vehicle adds its base fare, staying on adds only the per-km part.
        # with the per-km part alone, cheapest split one jeepney ride into two
        # short ones to save seconds and paid a second base fare (php 77 vs 64)
        from . import fares
        if edge.mode == "Walk":
            return 0.0
        walked = bool(arriving_mode) and arriving_mode.startswith("Walk<")
        boarding = arriving_mode is None or walked or vehicle_of(arriving_mode) != edge.mode
        raw = fares.marginal_fare(edge.mode, edge.distance_km)
        if boarding:
            raw += fares.mode_params(edge.mode)["base_php"]
        return min(1.0, raw / self._fare_scale)

    def edge_cost(self, edge: Edge, arriving_mode: str | None, profile: Profile) -> float:
        # profile-weighted cost of taking this edge.
        # the baseline is the paper's distance-based a*: it minimizes km, no
        # time basis and no criteria penalties at all.
        if profile.id == "baseline":
            return edge.distance_km
        c = self.criteria[edge.id]
        p = self.friction_norm(arriving_mode, edge.mode, edge.src)
        f = self.fare_norm(edge, arriving_mode)
        multiplier = 1.0 + profile.w_T * c.T + profile.w_F * f + profile.w_R * c.R + profile.w_P * p
        return edge.base_time * multiplier
