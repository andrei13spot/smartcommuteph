# import and export for the researcher dashboard.
# - parse_log_csv / summarize_log: read the same 360 row csv that the dashboard
#   exports (od_pair, profile, algorithm + the 8 kpis), check it, and work out
#   the sop answers that the log alone can support.
# - build_report_pdf: one pdf that answers sop 1 to 3, either from the live
#   benchmark or from an imported log.
from __future__ import annotations

import csv
import io
from datetime import datetime

import numpy as np

from .benchmark import KPI_COLUMNS, _paired, _rm_anova

REQUIRED_COLUMNS = ["od_pair", "profile", "algorithm", *KPI_COLUMNS]
MAX_IMPORT_BYTES = 2_000_000

# which logged kpi stands in for each profile's criterion when only the log is
# available. T and F match the live sop1 measure exactly. the live sop1 uses
# the mean flood risk and the transfer friction, which the log does not store,
# so R uses the worst-segment flood score and P the number of transfers.
LOG_CRITERION = {
    "T": ("ridership_density_score", "mean crowding (0-1)", True),
    "F": ("fare_php", "trip fare (PHP)", True),
    "R": ("flood_risk_score", "worst-segment flood risk (0-1)", False),
    "P": ("transfers", "number of transfers", False),
}
PROFILE_PRIORITY = {"uncrowded": "T", "cheapest": "F", "safest": "R", "convenient": "P"}
PROFILE_ORDER = ["uncrowded", "cheapest", "safest", "convenient"]


def parse_log_csv(text: str) -> list[dict]:
    # turn the csv text into typed rows, or raise ValueError with a reason a
    # person can act on
    if not text or not text.strip():
        raise ValueError("the file is empty")
    if len(text.encode("utf-8", "ignore")) > MAX_IMPORT_BYTES:
        raise ValueError("the file is larger than 2 MB, which is too big for a benchmark log")
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    header = [h.strip() for h in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise ValueError("missing columns: " + ", ".join(missing)
                         + ". Use a file made with Export CSV on this dashboard.")
    rows = []
    for i, raw in enumerate(reader, start=2):
        r = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
        if not any(r.values()):
            continue
        algo = r["algorithm"].lower()
        if algo not in ("framework", "baseline"):
            raise ValueError(f"line {i}: algorithm must be framework or baseline, not '{r['algorithm']}'")
        if "->" not in r["od_pair"]:
            raise ValueError(f"line {i}: od_pair should look like origin->destination")
        row = {"od_pair": r["od_pair"], "profile": r["profile"].lower(), "algorithm": algo}
        for k in KPI_COLUMNS:
            try:
                row[k] = float(r[k])
            except ValueError:
                raise ValueError(f"line {i}: {k} is not a number ('{r[k]}')") from None
        rows.append(row)
    if not rows:
        raise ValueError("the file has a header but no rows")
    return rows


def _ordered_profiles(rows: list[dict]) -> list[str]:
    found = {r["profile"] for r in rows}
    return [p for p in PROFILE_ORDER if p in found] + sorted(found - set(PROFILE_ORDER))


def summarize_log(rows: list[dict]) -> dict:
    # sop answers that can be computed from the 8 kpi log alone
    profiles = _ordered_profiles(rows)
    fw: dict[tuple[str, str], dict] = {}
    bl: dict[str, dict] = {}
    for r in rows:
        if r["algorithm"] == "framework":
            fw[(r["od_pair"], r["profile"])] = r
        else:
            # the baseline ignores the profile, so one row per od is enough
            bl.setdefault(r["od_pair"], r)
    ods = sorted({od for od, _ in fw} & set(bl))
    complete = [od for od in ods if all((od, p) in fw for p in profiles)]
    if not complete:
        raise ValueError("no origin and destination pair has both framework and baseline rows")

    warnings = []
    if len(rows) != 360:
        warnings.append(f"the file has {len(rows)} rows; a full benchmark log has 360")
    if len(complete) < len(ods):
        warnings.append(f"{len(ods) - len(complete)} pairs are missing a profile and were left out")

    # sop 1: each profile's criterion, framework vs baseline, paired by od
    sop1 = []
    for p in profiles:
        pri = PROFILE_PRIORITY.get(p)
        if pri is None:
            continue
        col, label, same_as_live = LOG_CRITERION[pri]
        b = [bl[od][col] for od in complete]
        f = [fw[(od, p)][col] for od in complete]
        stats = _paired(b, f)
        stats.update({
            "profile": p, "criterion": label, "column": col, "same_as_live": same_as_live,
            "significant": stats["p"] < 0.05,
            "direction": "framework_lower" if stats["mean_diff"] > 0 else
                         "framework_higher" if stats["mean_diff"] < 0 else "equal",
        })
        sop1.append(stats)

    # sop 2: different routes across profiles. the log has no route ids, so
    # two runs count as the same route when distance, time, fare and transfers
    # all match.
    distinct = []
    for od in complete:
        sigs = {(fw[(od, p)]["distance_km"], fw[(od, p)]["travel_time_min"],
                 fw[(od, p)]["fare_php"], fw[(od, p)]["transfers"]) for p in profiles}
        distinct.append(len(sigs))
    time_matrix = np.array([[fw[(od, p)]["travel_time_min"] for p in profiles] for od in complete])
    anova = _rm_anova(time_matrix) if len(profiles) >= 2 and len(complete) >= 3 else None
    sop2 = {
        "pairs_with_variance": int(sum(d >= 2 for d in distinct)),
        "pct_with_variance": round(100.0 * sum(d >= 2 for d in distinct) / len(distinct), 1),
        "mean_distinct_routes": round(float(np.mean(distinct)), 2),
        "rm_anova_travel_time": anova,
    }

    # sop 3: nodes expanded and time, baseline once per od vs the framework
    # mean over the profiles (same pairing as the live benchmark)
    b_nodes = [bl[od]["nodes_expanded"] for od in complete]
    f_nodes = [float(np.mean([fw[(od, p)]["nodes_expanded"] for p in profiles])) for od in complete]
    b_ms = [bl[od]["exec_ms"] for od in complete]
    f_ms = [float(np.mean([fw[(od, p)]["exec_ms"] for p in profiles])) for od in complete]
    sop3 = {"nodes": _paired(b_nodes, f_nodes), "exec_ms": _paired(b_ms, f_ms)}

    # mean of every kpi per profile and algorithm
    kpi_means = []
    for p in profiles:
        for algo, src in (("framework", [fw[(od, p)] for od in complete]),
                          ("baseline", [bl[od] for od in complete])):
            kpi_means.append({"profile": p, "algorithm": algo,
                              **{k: round(float(np.mean([r[k] for r in src])), 3) for k in KPI_COLUMNS}})

    return {
        "rows": len(rows), "od_pairs": len(complete), "profiles": profiles,
        "warnings": warnings, "sop1": sop1, "sop2": sop2, "sop3": sop3, "kpi_means": kpi_means,
    }


# ---------------------------------------------------------------- pdf report

def _ascii(s) -> str:
    # the built-in pdf fonts only cover latin-1
    s = str(s).replace("·", "-").replace("–", "-").replace("—", "-").replace("≥", ">=")
    return s.encode("latin-1", "replace").decode("latin-1")


def _p(v) -> str:
    return "< 0.001" if v is not None and v < 0.001 else f"{v:.4f}"


def _yes(b) -> str:
    return "Yes" if b else "No"


def build_report_pdf(log_summary: dict, live: dict | None = None, context: dict | None = None,
                     source: str = "live engine") -> bytes:
    from fpdf import FPDF

    ctx = context or {}
    pdf = FPDF(format="A4")
    pdf.set_margins(18, 16, 18)
    pdf.set_auto_page_break(True, margin=16)
    pdf.add_page()
    W = pdf.w - pdf.l_margin - pdf.r_margin

    def h1(t):
        pdf.set_font("Helvetica", "B", 16)
        pdf.multi_cell(W, 8, _ascii(t), new_x="LMARGIN", new_y="NEXT")

    def h2(t):
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 12)
        pdf.multi_cell(W, 7, _ascii(t), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    def para(t, size=10, style=""):
        pdf.set_font("Helvetica", style, size)
        pdf.multi_cell(W, 5, _ascii(t), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    def table(head, body, widths=None):
        pdf.set_font("Helvetica", "", 9)
        with pdf.table(col_widths=widths, text_align="LEFT", line_height=5,
                       first_row_as_headings=True) as t:
            row = t.row()
            for c in head:
                row.cell(_ascii(c))
            for r in body:
                row = t.row()
                for c in r:
                    row.cell(_ascii(c))
        pdf.ln(2)

    h1("SmartCommute PH - Benchmark Report")
    para(f"Generated {datetime.now().strftime('%d %B %Y, %H:%M')} from the {source}. "
         "Group 11, BSCS, PUP CCIS.", 9)

    # 1. run
    h2("1. Run conditions")
    s1 = log_summary["sop1"]
    rows = [["Data source", source],
            ["Origin and destination pairs", str(log_summary["od_pairs"])],
            ["Profiles", ", ".join(p.title() for p in log_summary["profiles"])],
            ["Paired observations", str(log_summary["od_pairs"] * len(log_summary["profiles"]))],
            ["Rows in the benchmark log", str(log_summary["rows"])],
            ["Baseline", "distance-based A* (cost = distance only)"]]
    if live:
        rows.insert(1, ["Hour and rainfall", f"hour {live.get('hour')}, {live.get('rainfall_mm')} mm"])
    for k in ("graph", "models", "weights"):
        if ctx.get(k):
            rows.append([{"graph": "Graph", "models": "Models", "weights": "AHP weights"}[k], ctx[k]])
    table(["Item", "Value"], rows, (60, W - 60))
    for w in log_summary.get("warnings", []):
        para("Note: " + w, 9, "I")

    # 2. summary
    h2("2. Hypothesis summary")
    if live:
        s2, s3 = live["sop2"], live["sop3"]
        sig = [p["name"] for p in live["per_profile"] if p["supported"]]
        rows = [
            ["SOP 1", "Does each profile's criterion differ from the baseline?", "Paired t-test per profile",
             f"Significant for {', '.join(sig) or 'none'}; framework value higher in "
             f"{sum(p['direction'] == 'framework_higher' for p in live['per_profile'])} of 4",
             "Partly" if sig and len(sig) < len(live["per_profile"]) else _yes(bool(sig))],
            ["SOP 2", "Do the profiles give different routes for the same trip?", "Jaccard + RM-ANOVA",
             f"{s2['pct_with_variance']}% of pairs differ; F {s2['rm_anova']['F']}, corrected p {_p(s2['rm_anova']['p_decision'])}",
             _yes(s2["supported"])],
            ["SOP 3", "Does the search space differ (nodes, time)?", "Paired t-test",
             f"nodes {s3['nodes']['mean_baseline']:.1f} vs {s3['nodes']['mean_framework']:.1f}, p {_p(s3['nodes']['p'])}; "
             "the framework expands more", _yes(s3["supported"]) + " (opposite direction)"],
        ]
    else:
        s2, s3 = log_summary["sop2"], log_summary["sop3"]
        sig = [r["profile"].title() for r in s1 if r["significant"]]
        a = s2["rm_anova_travel_time"]
        rows = [
            ["SOP 1", "Does each profile's criterion differ from the baseline?", "Paired t-test per profile",
             f"Significant for {', '.join(sig) or 'none'}", "Partly" if 0 < len(sig) < len(s1) else _yes(bool(sig))],
            ["SOP 2", "Do the profiles give different routes for the same trip?", "Route count + RM-ANOVA on time",
             f"{s2['pct_with_variance']}% of pairs differ" + (f"; F {a['F']}, corrected p {_p(a['p_decision'])}" if a else ""),
             _yes(s2["pairs_with_variance"] > 0 and (a is None or a["p_decision"] < 0.05))],
            ["SOP 3", "Does the search space differ (nodes, time)?", "Paired t-test",
             f"nodes {s3['nodes']['mean_baseline']:.1f} vs {s3['nodes']['mean_framework']:.1f}, p {_p(s3['nodes']['p'])}",
             _yes(s3["nodes"]["p"] < 0.05)],
        ]
    table(["SOP", "Question", "Test", "Result", "Supported"], rows, (14, 44, 30, W - 14 - 44 - 30 - 22, 22))

    # 3. sop 1
    h2("3. SOP 1 - Each profile's criterion against the distance baseline")
    if live:
        names = {"T": "mean crowding (0-1)", "F": "trip fare (PHP)", "R": "mean flood risk (0-1)",
                 "P": "transfer friction"}
        body = [[p["name"], names[p["priority"]], f"{p['mean_baseline']:.3f}", f"{p['mean_framework']:.3f}",
                 f"{p['t']:.3f}", _p(p["p"]), _yes(p["supported"]),
                 "higher" if p["direction"] == "framework_higher" else "lower"] for p in live["per_profile"]]
        n = live["per_profile"][0]["n"]
    else:
        body = [[r["profile"].title(), r["criterion"], f"{r['mean_baseline']:.3f}", f"{r['mean_framework']:.3f}",
                 f"{r['t']:.3f}", _p(r["p"]), _yes(r["significant"]),
                 "higher" if r["direction"] == "framework_higher" else "lower" if r["direction"] == "framework_lower" else "equal"]
                for r in s1]
        n = s1[0]["n"] if s1 else 0
    table(["Profile", "Criterion", "Baseline", "Framework", "t", "p", "p < 0.05", "Framework"],
          body, (22, 38, 18, 20, 16, 18, 18, W - 150))
    para(f"Paired-samples t-test, two-sided, alpha 0.05, n = {n} pairs per profile. "
         "A lower framework value means the framework improved that criterion.", 9)
    if live:
        para("Reading: the framework's value is higher than the baseline in every profile. Its cost is built on "
             "travel time, so it moves trips onto rail, the fastest mode, which in the model is the most crowded "
             "mode at 8 am and needs more transfers. A preference can at most double the cost of an edge.", 9)
    else:
        para("Taken from the imported log. Crowding and fare match the live test. Flood risk uses the worst "
             "segment and Convenient uses the number of transfers, because the log does not store the mean "
             "flood risk or the transfer friction.", 9, "I")

    # 4. sop 2
    h2("4. SOP 2 - Route differences across the four profiles")
    if live:
        a = s2["rm_anova"]
        rows = [["Pairs with at least two different routes", f"{round(s2['pct_with_variance'] * live['od_pairs'] / 100)} of {live['od_pairs']} ({s2['pct_with_variance']}%)"],
                ["Mean number of different routes per pair", str(s2["mean_distinct_routes"])],
                ["Mean Jaccard similarity", str(s2["mean_jaccard"])],
                ["RM-ANOVA F (df)", f"{a['F']} ({a['df'][0]}, {a['df'][1]})"],
                ["Mauchly's W, p", f"{a['mauchly_w']}, {_p(a['mauchly_p'])}"],
                ["Greenhouse-Geisser epsilon", str(a["gg_epsilon"])],
                ["Corrected p", _p(a["p_decision"])]]
        table(["Measure", "Value"], rows, (90, W - 90))
        para("The RM-ANOVA uses a profile-invariant route score (equal weights), so it only changes when the "
             "routes themselves differ.", 9)
    else:
        a = s2["rm_anova_travel_time"]
        rows = [["Pairs with at least two different routes", f"{s2['pairs_with_variance']} of {log_summary['od_pairs']} ({s2['pct_with_variance']}%)"],
                ["Mean number of different routes per pair", str(s2["mean_distinct_routes"])]]
        if a:
            rows += [["RM-ANOVA on travel time, F (df)", f"{a['F']} ({a['df'][0]}, {a['df'][1]})"],
                     ["Greenhouse-Geisser epsilon", str(a["gg_epsilon"])],
                     ["Corrected p", _p(a["p_decision"])]]
        table(["Measure", "Value"], rows, (90, W - 90))
        para("The log has no route ids, so two runs count as the same route when distance, time, fare and "
             "transfers all match. The Jaccard index needs the stations of each route and is only in the live report.",
             9, "I")

    # 5. sop 3
    h2("5. SOP 3 - Search space and execution time")
    n3, m3 = s3["nodes"], s3.get("exec_ms") or s3["exec_time_ms"]
    table(["Measure", "Baseline", "Framework", "t", "p", "n"],
          [["Nodes expanded", f"{n3['mean_baseline']:.1f}", f"{n3['mean_framework']:.1f}", f"{n3['t']:.3f}", _p(n3["p"]), str(n3["n"])],
           ["Execution time (ms)", f"{m3['mean_baseline']:.2f}", f"{m3['mean_framework']:.2f}", f"{m3['t']:.3f}", _p(m3["p"]), str(m3["n"])]],
          (50, 24, 24, 22, 22, W - 142))
    para("Paired at the origin and destination level: the baseline runs once per pair and is compared with the "
         "framework's mean over the four profiles. The framework expands more nodes: its time heuristic assumes "
         "60 km/h while most edges are jeepney at 20 km/h, and the preference multiplier raises the cost above "
         "travel time. Execution times change from run to run; the ratio is the stable part.", 9)

    # 6. kpis
    h2("6. The eight KPIs, mean per profile")
    labels = {"travel_time_min": "Time (min)", "distance_km": "Dist (km)", "fare_php": "Fare (PHP)",
              "transfers": "Transfers", "flood_risk_score": "Flood (max)", "ridership_density_score": "Crowding",
              "nodes_expanded": "Nodes", "exec_ms": "ms"}
    body = [[f"{r['profile'].title()} / {r['algorithm']}",
             *[f"{r[k]:.2f}" if k not in ("nodes_expanded",) else f"{r[k]:.0f}" for k in KPI_COLUMNS]]
            for r in log_summary["kpi_means"]]
    first = 36
    table(["Profile / run", *[labels[k] for k in KPI_COLUMNS]], body,
          (first, *([(W - first) / len(KPI_COLUMNS)] * len(KPI_COLUMNS))))

    # 7. models and weights
    if ctx.get("model_rows") or ctx.get("weight_rows"):
        h2("7. Models and AHP weights")
        if ctx.get("model_rows"):
            table(["Model", "Trained on", "Holdout error"], ctx["model_rows"], (40, W - 80, 40))
        if ctx.get("weight_rows"):
            table(["Profile", "W_T", "W_F", "W_R", "W_P", "CR", "Accepted"], ctx["weight_rows"],
                  (30, 20, 20, 20, 20, 20, W - 130))

    h2("Notes")
    for n_ in ctx.get("notes", []):
        para("- " + n_, 9)

    return bytes(pdf.output())


def live_context() -> dict:
    # graph, model and weight facts for the live report
    from ..ml import flood, ridership
    from ..profiles import PROFILES
    from ..routing.graph import load_graph
    from .ml_metrics import ml_metrics

    g = load_graph()
    m = {x["key"]: x for x in ml_metrics().get("models", [])}
    model_rows = []
    if "lstm" in m:
        model_rows.append(["LSTM (crowding)", "MRT-3 hourly ridership, January 2024 to December 2025 (14,024 hours)",
                           f"RMSE {m['lstm'].get('rmse')}"])
    for key, label, data in (("busway", "LSTM (EDSA busway)", "DOTr tally sheets, 21 stations, digitized"),
                             ("lrt2", "LSTM (LRT-2)", "LRTA entries by time band, 2024 to March 2026"),
                             ("lrt1", "LSTM (LRT-1)", "reconstructed: PSA monthly totals x MRT-3 hourly share")):
        if key in m:
            model_rows.append([label, data, f"RMSE {m[key].get('rmse')}"])
    if "rfr" in m:
        model_rows.append(["Random Forest (flood)", "flood rule with exposure from 764 MMDA incident points",
                           f"RMSE {m['rfr'].get('rmse')}, R2 {m['rfr'].get('r2')}"])
    weight_rows, source = [], ""
    for p in PROFILES.values():
        weight_rows.append([p.name, f"{p.w_T:.3f}", f"{p.w_F:.3f}", f"{p.w_R:.3f}", f"{p.w_P:.3f}",
                            f"{p.cr}" if p.cr is not None else "-",
                            f"{p.n_accepted} of {p.n_respondents}" if p.n_respondents else "-"])
        source = p.weights_source or source
    simulated = "simulated" in source.lower()
    return {
        "graph": f"{len(g.nodes)} nodes, {len(g.edges) // 2} edges, {len(g.real_nodes)} anchors",
        "models": f"LSTM {'trained' if ridership.predictor.trained else 'fallback curve'}, "
                  f"Random Forest {'trained' if flood.predictor.trained else 'fallback heuristic'}",
        "weights": "AHP pipeline on simulated respondents (survey not yet done)" if simulated else "AHP pipeline",
        "model_rows": model_rows,
        "weight_rows": weight_rows,
        "notes": [
            "The AHP weights come from simulated respondents until the commuter survey is done.",
            "The Random Forest learns a flood rule we set; its R2 is fit to that rule, not accuracy on observed floods.",
            "All results are for the conditions in section 1. Execution times vary from run to run.",
        ],
    }
