# benchmark: framework (multi-criteria a*) vs a distance-based baseline a*.
# answers the three research questions (sop1 cost reduction, sop2 route
# distinctness, sop3 search efficiency) over all c(10,2)=45 od pairs x 4 profiles.
from __future__ import annotations

import csv
import io
import time
from itertools import combinations

import numpy as np
from scipy import stats

from ..profiles import BASELINE, PROFILES
from ..routing.astar import shortest_route
from ..routing.cost import CostContext, transfer_friction
from ..routing.graph import load_graph


def _prioritized_value(ctx: CostContext, edges, priority: str) -> float:
    # the criterion the profile optimizes, aggregated over the route
    if not edges:
        return 0.0
    if priority == "R":
        return max(ctx.criteria[e.id].R for e in edges)
    if priority == "F":
        return sum(ctx.criteria[e.id].F for e in edges) / len(edges)
    if priority == "T":
        return sum(ctx.criteria[e.id].T for e in edges) / len(edges)
    # P = transfer friction along the path
    prev = None
    vals = []
    for e in edges:
        vals.append(ctx.friction_norm(prev, e.mode))
        prev = e.mode
    return sum(vals) / len(vals)


def _paired(baseline: list[float], framework: list[float]) -> dict:
    # paired t-test of framework vs baseline, plus mean percent reduction
    b = np.array(baseline, dtype=float)
    f = np.array(framework, dtype=float)
    diff = b - f  # positive means the framework lowered the criterion
    mean_b = float(b.mean()) if len(b) else 0.0
    mean_f = float(f.mean()) if len(f) else 0.0
    reduction_pct = ((mean_b - mean_f) / mean_b * 100.0) if mean_b > 1e-9 else 0.0
    if np.allclose(diff, 0.0):
        t, p = 0.0, 1.0  # no difference; t-test is undefined on zero variance
    else:
        res = stats.ttest_rel(b, f)
        t, p = float(res.statistic), float(res.pvalue)
    return {
        "mean_reduction_pct": round(reduction_pct, 2),
        "t": round(t, 3),
        "p": round(p, 4),
        "supported": bool(p < 0.05 and reduction_pct > 0),
    }


_CACHE: dict[tuple[int, float], dict] = {}


def run_benchmark(hour: int = 8, rainfall_mm: float = 30.0) -> dict:
    key = (hour, round(rainfall_mm, 1))
    if key in _CACHE:
        return _CACHE[key]

    graph = load_graph()
    ctx = CostContext(graph, hour=hour, rainfall_mm=rainfall_mm)
    od_pairs = list(combinations(graph.nodes, 2))

    crit_fw = {pid: [] for pid in PROFILES}
    crit_bl = {pid: [] for pid in PROFILES}
    nodes_fw, nodes_bl = [], []
    distinct_counts = []

    for o, d in od_pairs:
        base = shortest_route(graph, o, d, BASELINE, ctx)
        base_crit = {p: _prioritized_value(ctx, base.edges, prof.priority) for p, prof in PROFILES.items()}
        routes = set()
        for pid, prof in PROFILES.items():
            fw = shortest_route(graph, o, d, prof, ctx)
            routes.add(tuple(e.id for e in fw.edges))
            crit_fw[pid].append(_prioritized_value(ctx, fw.edges, prof.priority))
            crit_bl[pid].append(base_crit[pid])
            nodes_fw.append(fw.expanded_nodes)
            nodes_bl.append(base.expanded_nodes)
        distinct_counts.append(len(routes))

    # sop1: cost reduction on the prioritized criterion, per profile and pooled
    per_profile = []
    pooled_fw, pooled_bl = [], []
    for pid, prof in PROFILES.items():
        res = _paired(crit_bl[pid], crit_fw[pid])
        per_profile.append({"id": pid, "name": prof.name, "priority": prof.priority, **res})
        pooled_fw += crit_fw[pid]
        pooled_bl += crit_bl[pid]
    sop1 = _paired(pooled_bl, pooled_fw)
    # one-way anova across the four profiles' framework criterion values
    groups = [np.array(crit_fw[pid], dtype=float) for pid in PROFILES]
    try:
        anova = stats.f_oneway(*groups)
        anova_f = round(float(anova.statistic), 3)
    except Exception:
        anova_f = 0.0

    # sop2: route distinctness across profiles
    dc = np.array(distinct_counts, dtype=float)
    sop2 = {
        "mean_distinct_routes": round(float(dc.mean()), 2),
        "pct_with_variance": round(float((dc >= 2).mean() * 100.0), 1),
        "supported": bool((dc >= 2).any()),
    }

    # sop3: search-space efficiency (expanded nodes)
    sop3 = _paired(nodes_bl, nodes_fw)
    sop3["fw_nodes_mean"] = round(float(np.mean(nodes_fw)), 1)
    sop3["bl_nodes_mean"] = round(float(np.mean(nodes_bl)), 1)

    result = {
        "observations": len(od_pairs) * len(PROFILES),
        "od_pairs": len(od_pairs),
        "profiles": len(PROFILES),
        "test": "Paired-Samples T-Test",
        "alpha": 0.05,
        "hour": hour,
        "rainfall_mm": rainfall_mm,
        "sop1": {"title": "Cost reduction per profile", "anova_f": anova_f, **sop1},
        "sop2": {"title": "Route distinctness across profiles", **sop2},
        "sop3": {"title": "Search-space efficiency", **sop3},
        "per_profile": per_profile,
    }
    _CACHE[key] = result
    return result


# ---- 360 row benchmark log ----
# one row per (od pair, profile, algorithm): 45 x 4 x 2 = 360 rows,
# each with the 8 kpis. this is what dave's data pipeline check reads.

KPI_COLUMNS = [
    "travel_time_min", "distance_km", "fare_php", "transfers",
    "flood_risk_score", "ridership_density_score", "nodes_expanded", "exec_ms",
]


def _count_transfers(edges) -> int:
    modes = []
    for e in edges:
        if not modes or modes[-1] != e.mode:
            modes.append(e.mode)
    return max(0, len(modes) - 1)


def _kpis(ctx: CostContext, res, exec_ms: float) -> dict:
    # the 8 kpis for one run
    edges = res.edges
    transfer_min = 0.0
    prev = None
    for e in edges:
        transfer_min += transfer_friction(prev, e.mode)
        prev = e.mode
    return {
        "travel_time_min": round(sum(e.base_time for e in edges) + transfer_min, 2),
        "distance_km": round(sum(e.distance_km for e in edges), 2),
        "fare_php": round(sum(e.fare for e in edges), 1),
        "transfers": _count_transfers(edges),
        "flood_risk_score": round(max((ctx.criteria[e.id].R for e in edges), default=0.0), 3),
        "ridership_density_score": round(
            sum(ctx.criteria[e.id].T for e in edges) / len(edges), 3) if edges else 0.0,
        "nodes_expanded": res.expanded_nodes,
        "exec_ms": exec_ms,
    }


_LOG_CACHE: dict[tuple[int, float], list[dict]] = {}


def run_benchmark_log(hour: int = 8, rainfall_mm: float = 30.0) -> list[dict]:
    key = (hour, round(rainfall_mm, 1))
    if key in _LOG_CACHE:
        return _LOG_CACHE[key]

    graph = load_graph()
    ctx = CostContext(graph, hour=hour, rainfall_mm=rainfall_mm)
    rows: list[dict] = []
    for o, d in combinations(graph.nodes, 2):
        for pid, prof in PROFILES.items():
            for algo, p in (("framework", prof), ("baseline", BASELINE)):
                t0 = time.perf_counter()
                res = shortest_route(graph, o, d, p, ctx)
                ms = round((time.perf_counter() - t0) * 1000.0, 3)
                rows.append({
                    "od_pair": f"{o}->{d}", "profile": pid, "algorithm": algo,
                    **_kpis(ctx, res, ms),
                })
    _LOG_CACHE[key] = rows
    return rows


def benchmark_log_csv(hour: int = 8, rainfall_mm: float = 30.0) -> str:
    rows = run_benchmark_log(hour, rainfall_mm)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["od_pair", "profile", "algorithm", *KPI_COLUMNS])
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()
