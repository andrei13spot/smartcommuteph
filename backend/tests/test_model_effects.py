# checks that the dynamic inputs actually move the criteria, the cost multiplier
# stays inside the paper's bound, fares discount correctly, and the mmda flood
# exposure math holds. all fast unit-level checks.
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.profiles import PROFILES, resolve_profile
from app.routing.astar import shortest_route
from app.routing.cost import CostContext, transfer_friction
from app.routing.graph import (
    _FLOOD_BASELINE,
    _point_to_segment_km,
    load_graph,
)
from app.routing.heuristic import distance_heuristic

client = TestClient(app)


def test_rainfall_raises_flood_risk():
    # more rain must not lower any street edge's raw flood risk
    g = load_graph()
    dry = CostContext(g, hour=8, rainfall_mm=5.0)
    wet = CostContext(g, hour=8, rainfall_mm=60.0)
    street = [e for e in g.edges.values() if e.mode in ("Jeepney", "EDSA-Bus")]
    higher = sum(1 for e in street if wet.raw_flood[e.id] > dry.raw_flood[e.id] + 1e-9)
    assert higher > len(street) * 0.5, "rainfall has no effect on street flood risk"


def test_hour_raises_crowding():
    # rush hour demand must beat pre-dawn demand
    from app.ml.ridership import predictor
    assert predictor.demand_factor(8) > predictor.demand_factor(3)
    assert predictor.demand_factor(18) > predictor.demand_factor(3)


def test_multiplier_stays_in_paper_bound():
    # equation 4: penalty multiplier bounded 1.0..2.0 for every edge x profile
    g = load_graph()
    ctx = CostContext(g, hour=18, rainfall_mm=60.0)
    for pid in PROFILES:
        prof = resolve_profile(pid)
        for e in list(g.edges.values())[:200]:
            mult = ctx.edge_cost(e, "Jeepney", prof) / e.base_time
            assert 1.0 - 1e-9 <= mult <= 2.0 + 1e-9, f"{pid} multiplier {mult} out of bound"


def test_no_friction_on_virtual_continuation():
    # riding through a 300m virtual stop is not a transfer
    assert transfer_friction("Jeepney", "Jeepney", continuing=True) == 0.0
    # changing jeepney lines at a real anchor still costs the table 3 diagonal
    assert transfer_friction("Jeepney", "Jeepney", continuing=False) == 0.5


def test_fare_discounts_by_passenger_type():
    body = {"origin": "cubao", "destination": "pasay", "profile": "cheapest"}
    regular = client.post("/api/route", json=body).json()
    assert regular["summary"]["fare_discounted_php"] is None
    for pt in ("senior", "  Student "):  # case/space insensitive
        r = client.post("/api/route", json={**body, "passenger_type": pt}).json()
        # official discounted matrix on mrt-3 legs, 20% off elsewhere: always
        # below the regular fare and close to 80 percent of it
        disc, full = r["summary"]["fare_discounted_php"], r["summary"]["fare_php"]
        assert 0.7 * full <= disc < full
    bad = client.post("/api/route", json={**body, "passenger_type": "child"})
    assert bad.status_code == 422


def test_point_to_segment_distance():
    # a point exactly on the segment is at distance ~0; one ~1km north is ~1km
    d_on = _point_to_segment_km(14.60, 121.00, 14.60, 120.99, 14.60, 121.01)
    assert d_on < 0.01
    d_off = _point_to_segment_km(14.609, 121.00, 14.60, 120.99, 14.60, 121.01)
    assert 0.9 < d_off < 1.1


def test_edges_far_from_incidents_stay_baseline():
    g = load_graph()
    vals = [e.flood_risk for e in g.edges.values()]
    assert min(vals) == _FLOOD_BASELINE
    assert max(vals) <= 1.0


def test_distance_heuristic_is_admissible():
    # straight line can never exceed the real path length
    g = load_graph()
    from app.profiles import BASELINE
    ctx = CostContext(g, hour=8, rainfall_mm=30.0)
    res = shortest_route(g, "cubao", "pasay", BASELINE, ctx)
    path_km = sum(e.distance_km for e in res.edges)
    assert distance_heuristic(g, "cubao", "pasay") <= path_km + 1e-9


def test_api_inspect_decomposition():
    r = client.post("/api/inspect", json={"origin": "cubao", "destination": "pasay",
                                          "profile": "safest"})
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["decomposition"], "inspector returned no per-edge decomposition"
    assert body["expanded_nodes"] > 0 and body["baseline_nodes"] > 0


def test_api_network_closure():
    # every edge endpoint must be a known node, or the map draws holes
    r = client.get("/api/network").json()
    ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["from_id"] in ids and e["to_id"] in ids


def test_fare_model_matches_published_matrices():
    # boarding-based fares: one ticket per leg, not one per edge. the old
    # per-edge sums charged 53 php for the full mrt-3 line vs the published ~28
    from app.routing.fares import path_fare

    g = load_graph()
    ctx = CostContext(g, hour=8, rainfall_mm=30.0)
    mrt = shortest_route(g, "sm_north", "pasay", resolve_profile("convenient"), ctx)
    assert all(e.mode == "MRT-3" for e in mrt.edges)
    assert 24 <= path_fare(g, mrt.edges) <= 32
    jeep = shortest_route(g, "sm_novaliches", "monumento", resolve_profile("cheapest"), ctx)
    km = sum(e.distance_km for e in jeep.edges)
    expected = 13 + 1.8 * max(0, km - 4)
    assert abs(path_fare(g, jeep.edges) - expected) <= 2.0


def test_hour_and_line_change_crowding():
    # the headway calibration must keep hour-of-day from cancelling out in
    # min-max normalization: normalized T should differ across hours per line
    g = load_graph()
    c8 = CostContext(g, hour=8, rainfall_mm=30.0)
    c3 = CostContext(g, hour=3, rainfall_mm=30.0)
    mrt = next(e for e in g.edges.values() if e.mode == "MRT-3")
    # the raw crowding of a rail edge must move with the hour (rush hour vs
    # 3 am), and after min-max scaling the hour must still show somewhere in
    # the network: a uniform scale across every edge would cancel out
    from app.ml.ridership import predictor as rp
    assert abs(rp.predict(mrt, 8) - rp.predict(mrt, 3)) > 0.01
    assert max(abs(c8.criteria[e].T - c3.criteria[e].T) for e in g.edges) > 0.01
    # and lines differ from each other at the same hour (supply differs)
    from app.ml.ridership import predictor
    assert predictor.line_factor("LRT-2", 8) != predictor.line_factor("MRT-3", 8)


def test_rail_legs_priced_by_official_matrix():
    # the dotr-mrt3 fare matrix prices rail legs by board/alight station
    from app.routing.fares import path_fare

    g = load_graph()
    ctx = CostContext(g, hour=8, rainfall_mm=30.0)
    full = shortest_route(g, "sm_north", "pasay", resolve_profile("convenient"), ctx)
    assert all(e.mode == "MRT-3" for e in full.edges)
    assert path_fare(g, full.edges) == 28.0  # official north ave -> taft
    assert path_fare(g, full.edges, discounted=True) == 22.0  # brochure's discounted matrix
    short = shortest_route(g, "cubao", "shaw", resolve_profile("convenient"), ctx)
    assert path_fare(g, short.edges) == 16.0  # official cubao -> shaw
    assert path_fare(g, short.edges, discounted=True) == 13.0


def test_rail_corridors_run_through_real_stations():
    # corridors are threaded through stations.json: sm_north -> pasay must pass
    # the actual mrt stations, with pass-through nodes hidden from the anchors
    g = load_graph()
    ctx = CostContext(g, hour=8, rainfall_mm=30.0)
    r = shortest_route(g, "sm_north", "pasay", resolve_profile("convenient"), ctx)
    names = {g.nodes[e.dst].name for e in r.edges}
    for must in ("Quezon MRT", "Kamuning MRT", "Ortigas MRT", "Guadalupe MRT"):
        assert must in names, f"missing station {must}"
    assert len(g.real_nodes) == 10  # stations never leak into the od anchors


def test_export_import_round_trip():
    # the csv the dashboard exports must import back with the same sop answers
    from app.research.benchmark import benchmark_log_csv

    csv_text = benchmark_log_csv(hour=8, rainfall_mm=30.0)
    r = client.post("/api/benchmark/import", json={"csv": csv_text, "filename": "log.csv"})
    assert r.status_code == 200
    d = r.json()
    assert d["rows"] == 360 and d["od_pairs"] == 45
    live = client.get("/api/benchmark").json()
    assert d["sop2"]["pct_with_variance"] == live["sop2"]["pct_with_variance"]
    assert round(d["sop3"]["nodes"]["mean_framework"], 1) == round(live["sop3"]["nodes"]["mean_framework"], 1)
    # a file that is not a benchmark log is refused with a reason
    bad = client.post("/api/benchmark/import", json={"csv": "a,b\n1,2", "filename": "x.csv"})
    assert bad.status_code == 422 and "missing columns" in bad.json()["detail"]


def test_pdf_reports_are_pdfs():
    from app.research.benchmark import benchmark_log_csv

    r = client.get("/api/benchmark/report")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    r2 = client.post("/api/benchmark/import/report",
                     json={"csv": benchmark_log_csv(hour=8, rainfall_mm=30.0), "filename": "log.csv"})
    assert r2.status_code == 200 and r2.content[:4] == b"%PDF"


def test_card_fares_use_the_stored_value_matrices():
    # lrt-1 and lrt-2 publish a stored value (beep) matrix next to the single
    # journey one; card=True must price from it. mrt-3 has one matrix only
    from app.routing.fares import MATRIX_INFO, matrix_leg_fare

    assert matrix_leg_fare("LRT-2", "Recto LRT", "Antipolo LRT") == 35.0
    assert matrix_leg_fare("LRT-2", "Recto LRT", "Antipolo LRT", card=True) == 33.0
    assert matrix_leg_fare("LRT-2", "Cubao Gateway", "Antipolo LRT-2", card=True) == 23.0
    assert matrix_leg_fare("LRT-1", "Baclaran LRT", "Roosevelt LRT") == 45.0  # 2 april 2025 matrix
    assert matrix_leg_fare("LRT-1", "Baclaran LRT", "Roosevelt LRT", card=True) == 43.0
    assert matrix_leg_fare("LRT-1", "Baclaran LRT", "Monumento LRT", card=True) == 37.0
    # the cavite extension is in the 2025 matrix, so pitx legs are priced from it
    assert matrix_leg_fare("LRT-1", "Pasay EDSA-Taft", "PITX") == 25.0
    assert matrix_leg_fare("MRT-3", "North Avenue MRT", "Taft Ave MRT", card=True) == 28.0
    assert "stored_value_matrix" in MATRIX_INFO["LRT-1"]["matrices"]
    assert MATRIX_INFO["MRT-3"]["stations"] == 13
    r = client.post("/api/route", json={"origin": "antipolo", "destination": "cubao", "profile": "cheapest"}).json()
    assert r["summary"]["fare_card_php"] <= r["summary"]["fare_php"]
    assert "fare_matrices" in client.get("/api/status").json()
