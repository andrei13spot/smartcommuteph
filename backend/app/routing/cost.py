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
# a walking transfer splits one table-3 transfer into two steps without making
# it cheaper: x -> walk -> jeepney costs table3[x][jeepney] (the walk takes all
# but the 0.5 jeepney boarding), jeepney -> walk -> jeepney costs the 0.5 line
# change, and walk -> x costs what jeepney -> x does.
_FRICTION_MATRIX["Jeepney"]["Walk"] = 0.0
for _m in ("LRT-1", "LRT-2", "MRT-3", "EDSA-Bus"):
    _FRICTION_MATRIX[_m]["Walk"] = _FRICTION_MATRIX[_m]["Jeepney"] - _FRICTION_MATRIX["Jeepney"]["Jeepney"]
_FRICTION_MATRIX["Walk"] = {**{m: _FRICTION_MATRIX["Jeepney"][m] for m in ("LRT-1", "LRT-2", "MRT-3", "EDSA-Bus")},
                            "Jeepney": _FRICTION_MATRIX["Jeepney"]["Jeepney"], "Walk": 0.0}
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
        prev = e.mode
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
            # F' = fare intensity of the edge (the per-km marginal cost of its
            # mode). boarding base fares are path-dependent and show up in the
            # reported total via path_fare; the per-boarding pain is already
            # penalized by the transfer term P'.
            raw_F[eid] = fares.marginal_fare(edge.mode, edge.distance_km)
            raw_R[eid] = fv

        T, F, R = (_min_max_scaled(r) for r in (raw_T, raw_F, raw_R))
        self.criteria: dict[str, EdgeCriteria] = {
            eid: EdgeCriteria(T=T[eid], F=F[eid], R=R[eid]) for eid in graph.edges
        }
        self.raw_flood = raw_R  # raw (un-normalized) flood values, read by the rainfall-effect test

    def friction_norm(self, arriving_mode: str | None, edge_mode: str,
                      src_id: str | None = None) -> float:
        # P' = normalized transfer friction. src_id is where the transition
        # happens: at a virtual stop the ride just continues (no transfer).
        continuing = bool(src_id) and self.graph.nodes[src_id].virtual
        return transfer_friction(arriving_mode, edge_mode, continuing) / _MAX_FRICTION

    def edge_cost(self, edge: Edge, arriving_mode: str | None, profile: Profile) -> float:
        # profile-weighted cost of taking this edge.
        # the baseline is the paper's distance-based a*: it minimizes km, no
        # time basis and no criteria penalties at all.
        if profile.id == "baseline":
            return edge.distance_km
        c = self.criteria[edge.id]
        p = self.friction_norm(arriving_mode, edge.mode, edge.src)
        multiplier = 1.0 + profile.w_T * c.T + profile.w_F * c.F + profile.w_R * c.R + profile.w_P * p
        return edge.base_time * multiplier
