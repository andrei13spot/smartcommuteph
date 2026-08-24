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
    # the criterion the profile optimizes, measured on the whole route in the
    # unit a commuter would recognize: total fare (php), total raw transfer
    # friction, worst-segment flood risk, mean crowding along the ride.
    if not edges:
        return 0.0
    if priority == "R":
        # mean flood risk along the route (table 7 in the paper defines the
        # flood criterion as the mean, not the worst segment)
        return sum(ctx.criteria[e.id].R for e in edges) / len(edges)
    if priority == "F":
        return float(sum(e.fare for e in edges))
    if priority == "T":
        return sum(ctx.criteria[e.id].T for e in edges) / len(edges)
    # P = total raw transfer friction actually paid along the path
    prev = None
    total = 0.0
    for e in edges:
        total += transfer_friction(prev, e.mode,
                                   continuing=ctx.graph.nodes[e.src].virtual)
        prev = e.mode
    return total


def _paired(baseline: list[float], framework: list[float]) -> dict:
    # paired t-test of framework vs baseline (equation 9), with the descriptive
    # statistics the paper reports alongside it: mean difference m_d and the
    # standard deviation of differences s_d (equations 10-11).
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
        "mean_baseline": round(mean_b, 3),
        "mean_framework": round(mean_f, 3),
        "mean_diff": round(float(diff.mean()) if len(diff) else 0.0, 4),
        "sd_diff": round(float(diff.std(ddof=1)) if len(diff) > 1 else 0.0, 4),
        "n": int(len(diff)),
        "mean_reduction_pct": round(reduction_pct, 2),
        "t": round(t, 3),
        "p": round(p, 4),
        "supported": bool(p < 0.05 and reduction_pct > 0),
    }


def _jaccard(a: set, b: set) -> float:
    # equation 12: |A n B| / |A u B| over the node sets of two routes
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def _reference_cost(ctx: CostContext, edges) -> float:
    # profile-INVARIANT score of a route: equation 4 with equal weights (0.25
    # each). the rm-anova for route distinctness must score every profile's
    # returned route with ONE fixed measure - scoring each route under its own
    # profile weights makes the anova react to the weight vectors themselves
    # (a router pinned to a single path still comes out "significant").
    total = 0.0
    prev = None
    for e in edges:
        c = ctx.criteria[e.id]
        p = ctx.friction_norm(prev, e.mode, e.src)
        total += e.base_time * (1.0 + 0.25 * (c.T + c.F + c.R + p))
        prev = e.mode
    return total


def _rm_anova(matrix: np.ndarray) -> dict:
    # repeated-measures anova (equations 13-18): rows = od pairs (subjects),
    # columns = the k=4 profiles (within-subjects factor). also reports
    # mauchly's w and the greenhouse-geisser epsilon (equation 19).
    n, k = matrix.shape
    grand = matrix.mean()
    profile_means = matrix.mean(axis=0)   # x_i.
    subject_means = matrix.mean(axis=1)   # x_.j
    ss_between = n * float(((profile_means - grand) ** 2).sum())
    ss_subjects = k * float(((subject_means - grand) ** 2).sum())
    ss_total = float(((matrix - grand) ** 2).sum())
    ss_residual = ss_total - ss_between - ss_subjects
    df_between = k - 1
    df_residual = (k - 1) * (n - 1)
    ms_between = ss_between / df_between
    ms_residual = ss_residual / df_residual if df_residual else 0.0
    F = ms_between / ms_residual if ms_residual > 1e-12 else 0.0
    p = float(stats.f.sf(F, df_between, df_residual)) if ms_residual > 1e-12 else 1.0

    # sphericity: orthonormal contrasts of the covariance matrix
    cov = np.cov(matrix, rowvar=False)
    # helmert-style orthonormal contrast matrix (k-1 x k)
    C = []
    for i in range(1, k):
        row = np.zeros(k)
        row[:i] = 1.0 / i
        row[i] = -1.0
        C.append(row / np.linalg.norm(row))
    C = np.array(C)
    s_star = C @ cov @ C.T
    eig = np.linalg.eigvalsh(s_star)
    eig = np.clip(eig, 1e-12, None)
    mean_eig = eig.mean()
    mauchly_w = float(np.prod(eig / mean_eig))
    # mauchly's chi-square significance test, so the paper's decision rule
    # (apply greenhouse-geisser when sphericity is violated) actually has a p
    kk = k - 1  # contrast dimension
    correction = 1.0 - (2 * kk * kk + kk + 2) / (6.0 * kk * (n - 1))
    chi2_stat = -(n - 1) * correction * float(np.log(max(mauchly_w, 1e-300)))
    mauchly_df = kk * (kk + 1) / 2 - 1
    mauchly_p = float(stats.chi2.sf(chi2_stat, mauchly_df))
    gg_eps = float(eig.sum() ** 2 / ((k - 1) * (eig ** 2).sum()))
    # greenhouse-geisser corrected p (applied when sphericity is in doubt)
    p_gg = float(stats.f.sf(F, df_between * gg_eps, df_residual * gg_eps)) if F > 0 else 1.0
    sphericity_violated = mauchly_p < 0.05
    # the paper's rule: report F with the gg correction when mauchly rejects
    p_decision = p_gg if sphericity_violated else p

    return {
        "F": round(F, 3),
        "df": [df_between, df_residual],
        "p": round(p, 4),
        "mauchly_w": round(mauchly_w, 4),
        "mauchly_p": round(mauchly_p, 4),
        "sphericity_violated": sphericity_violated,
        "gg_epsilon": round(gg_eps, 4),
        "p_gg_corrected": round(p_gg, 4),
        "p_decision": round(p_decision, 4),
        "ss": {"between_profiles": round(ss_between, 3),
               "subjects": round(ss_subjects, 3),
               "residual": round(ss_residual, 3),
               "total": round(ss_total, 3)},
    }


_CACHE: dict[tuple[int, float], dict] = {}


def run_benchmark(hour: int = 8, rainfall_mm: float = 30.0) -> dict:
    key = (hour, round(rainfall_mm, 1))
    if key in _CACHE:
        return _CACHE[key]

    graph = load_graph()
    ctx = CostContext(graph, hour=hour, rainfall_mm=rainfall_mm)
    # od pairs come from the 10 real anchors only, virtual jeepney stops are
    # path-through nodes, not origins/destinations. keeps it c(10,2) = 45
    od_pairs = list(combinations(graph.real_nodes, 2))

    crit_fw = {pid: [] for pid in PROFILES}
    crit_bl = {pid: [] for pid in PROFILES}
    od_nodes_fw, od_nodes_bl = [], []   # one entry per od (no pseudo-replication)
    od_ms_fw, od_ms_bl = [], []
    distinct_counts = []
    jaccard_means = []          # mean pairwise jaccard per od (equation 12)
    ref_cost_matrix = []        # x_ij: profile-invariant route score (rm-anova dv)
    own_cost_matrix = []        # each profile's own weighted cost (sensitivity only)

    for o, d in od_pairs:
        t0 = time.perf_counter()
        base = shortest_route(graph, o, d, BASELINE, ctx)
        base_ms = (time.perf_counter() - t0) * 1000.0
        base_crit = {p: _prioritized_value(ctx, base.edges, prof.priority) for p, prof in PROFILES.items()}
        routes = set()
        node_sets = []
        ref_row, own_row = [], []
        fw_nodes_row, fw_ms_row = [], []
        for pid, prof in PROFILES.items():
            t0 = time.perf_counter()
            fw = shortest_route(graph, o, d, prof, ctx)
            fw_ms = (time.perf_counter() - t0) * 1000.0
            routes.add(tuple(e.id for e in fw.edges))
            node_sets.append({e.src for e in fw.edges} | {e.dst for e in fw.edges})
            ref_row.append(_reference_cost(ctx, fw.edges))
            own_row.append(fw.total_cost)
            crit_fw[pid].append(_prioritized_value(ctx, fw.edges, prof.priority))
            crit_bl[pid].append(base_crit[pid])
            fw_nodes_row.append(fw.expanded_nodes)
            fw_ms_row.append(fw_ms)
        distinct_counts.append(len(routes))
        pairs = [(a, b) for i, a in enumerate(node_sets) for b in node_sets[i + 1:]]
        jaccard_means.append(sum(_jaccard(a, b) for a, b in pairs) / len(pairs))
        ref_cost_matrix.append(ref_row)
        own_cost_matrix.append(own_row)
        # od-level efficiency pairing: the baseline runs once per od, so it is
        # paired once per od against the framework's mean over the 4 profiles
        # (duplicating the one baseline run 4x would fake n=180 and inflate t)
        od_nodes_fw.append(float(np.mean(fw_nodes_row)))
        od_nodes_bl.append(float(base.expanded_nodes))
        od_ms_fw.append(float(np.mean(fw_ms_row)))
        od_ms_bl.append(base_ms)

    # sop1: prioritized criterion per profile, framework vs baseline.
    # no pooled t-test across profiles - fare is in php while the other three
    # are unitless 0..1, pooling them into one test mixes units. the paper's
    # h1 is two-sided ("differs significantly"), so supported = p < 0.05 with
    # the direction reported alongside.
    per_profile = []
    for pid, prof in PROFILES.items():
        res = _paired(crit_bl[pid], crit_fw[pid])
        res["supported"] = bool(res["p"] < 0.05)  # two-sided per h1
        res["direction"] = ("framework_lower" if res["mean_diff"] > 0
                            else "framework_higher" if res["mean_diff"] < 0 else "no_difference")
        per_profile.append({"id": pid, "name": prof.name, "priority": prof.priority, **res})
    # unit-safe headline: mean of the per-profile percentage reductions
    mean_reduction = float(np.mean([p["mean_reduction_pct"] for p in per_profile]))
    sop1 = {
        "mean_reduction_pct": round(mean_reduction, 2),
        "note": "mean of the four per-profile reduction percentages (unitless); "
                "see per_profile for the individual paired t-tests",
        "supported": bool(any(p["supported"] and p["mean_reduction_pct"] > 0 for p in per_profile)),
    }

    # sop2: route distinctness - topological (jaccard, eq 12) and statistical
    # (rm-anova, eqs 13-19) on a PROFILE-INVARIANT score of each returned route.
    # the own-weight anova is kept separately as a weight-sensitivity statistic;
    # it cannot evidence route distinctness (identical routes still differ in
    # own-weight cost), so it never gates the verdict.
    dc = np.array(distinct_counts, dtype=float)
    rm = _rm_anova(np.array(ref_cost_matrix, dtype=float))
    rm_own = _rm_anova(np.array(own_cost_matrix, dtype=float))
    sop2 = {
        "mean_distinct_routes": round(float(dc.mean()), 2),
        "pct_with_variance": round(float((dc >= 2).mean() * 100.0), 1),
        "mean_jaccard": round(float(np.mean(jaccard_means)), 4),
        "rm_anova": rm,
        "rm_anova_weight_sensitivity": {
            **rm_own,
            "note": "own-weight cost per profile: reacts to the weight vectors, "
                    "NOT route distinctness - do not cite as sop2 evidence",
        },
        # distinct routes must exist AND the invariant-score anova must agree
        "supported": bool((dc >= 2).any() and rm["p_decision"] < 0.05),
    }

    # sop3: search-space efficiency, od-level pairing (n = 45), both metrics,
    # two-sided per h1, with the direction stated explicitly
    sop3_nodes = _paired(od_nodes_bl, od_nodes_fw)
    sop3_time = _paired(od_ms_bl, od_ms_fw)
    sop3 = {
        "nodes": sop3_nodes,
        "exec_time_ms": sop3_time,
        "n_pairs": len(od_pairs),
        "fw_nodes_mean": round(float(np.mean(od_nodes_fw)), 1),
        "bl_nodes_mean": round(float(np.mean(od_nodes_bl)), 1),
        "fw_ms_mean": round(float(np.mean(od_ms_fw)), 3),
        "bl_ms_mean": round(float(np.mean(od_ms_bl)), 3),
        "direction": ("framework_expands_more" if np.mean(od_nodes_fw) > np.mean(od_nodes_bl)
                      else "framework_expands_fewer"),
        # h1 is two-sided on efficiency: a significant difference on either
        # metric counts, whichever direction it lands
        "supported": bool(sop3_nodes["p"] < 0.05 or sop3_time["p"] < 0.05),
    }

    result = {
        "observations": len(od_pairs) * len(PROFILES),
        "od_pairs": len(od_pairs),
        "profiles": len(PROFILES),
        "test": "Paired-Samples T-Test",
        "alpha": 0.05,
        "hour": hour,
        "rainfall_mm": rainfall_mm,
        "sop1": {"title": "Cost reduction per profile", **sop1},
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
        transfer_min += transfer_friction(prev, e.mode,
                                          continuing=ctx.graph.nodes[e.src].virtual)
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
    for o, d in combinations(graph.real_nodes, 2):
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
