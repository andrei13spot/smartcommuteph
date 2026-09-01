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
    haversine_km,
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
        assert abs(r["summary"]["fare_discounted_php"] - r["summary"]["fare_php"] * 0.8) < 0.11
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


def test_pagasa_fallback_is_offline_default():
    import os
    from app.ml import flood
    os.environ.pop("SCPH_PAGASA_TOKEN", None)
    flood._rain_cache.update(value=None, at=0.0)
    assert flood.fetch_pagasa_rainfall_mm() == flood.DEFAULT_RAINFALL_MM
    assert "default" in flood.rainfall_source()


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
    from app.profiles import resolve_profile
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
    assert abs(c8.criteria[mrt.id].T - c3.criteria[mrt.id].T) > 0.01
    # and lines differ from each other at the same hour (supply differs)
    from app.ml.ridership import predictor
    assert predictor.line_factor("LRT-2", 8) != predictor.line_factor("MRT-3", 8)
