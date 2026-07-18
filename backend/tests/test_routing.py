# checks on the routing engine and the api: a route is found, the heuristic is a
# lower bound, and the four profiles can produce different routes.
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.profiles import PROFILES, resolve_profile
from app.routing.astar import shortest_route
from app.routing.cost import CostContext
from app.routing.graph import MAX_SPEED_KMH, load_graph
from app.routing.heuristic import time_heuristic

client = TestClient(app)


def _ctx(hour: int = 8, rainfall: float = 30.0) -> CostContext:
    return CostContext(load_graph(), hour=hour, rainfall_mm=rainfall)


def test_graph_is_bidirectional_and_connected():
    g = load_graph()
    assert len(g.nodes) == 10
    # every forward edge has a reverse
    for e in list(g.edges.values()):
        assert f"{e.dst}->{e.src}:{e.mode}" in g.edges


def test_route_found_cubao_to_pasay():
    g = load_graph()
    res = shortest_route(g, "cubao", "pasay", resolve_profile("safest"), _ctx())
    assert res.found
    assert res.edges[0].src == "cubao"
    assert res.edges[-1].dst == "pasay"
    assert res.expanded_nodes > 0


def test_heuristic_is_admissible():
    # h(n) must never be bigger than the real straight-line travel time
    g = load_graph()
    res = shortest_route(g, "cubao", "pasay", resolve_profile("safest"), _ctx())
    h0 = time_heuristic(g, "cubao", "pasay")
    base_time = sum(e.base_time for e in res.edges)
    assert h0 <= base_time + 1e-6
    expected = g.straight_line_km("cubao", "pasay") / MAX_SPEED_KMH * 60.0
    assert abs(h0 - expected) < 1e-6


def test_framework_can_produce_distinct_routes():
    # route variance is tradeoff-dependent: it only shows up for od pairs that
    # have a time-competitive alternative within the 2x cost cap. on the coarse
    # 10-anchor graph with real mode speeds, fast rail wins most corridors, so
    # variance is sparse (mostly from avoiding transfers). it should get much
    # wider on the dense 300-500 node graph with 300m jeepney nodes. here we just
    # check the mechanism works: at least one od pair gives >= 2 distinct routes.
    from itertools import combinations

    g = load_graph()
    ctx = _ctx(hour=18, rainfall=45.0)
    divergent = 0
    for o, d in combinations(g.nodes, 2):
        paths = {
            pid: tuple(e.id for e in shortest_route(g, o, d, resolve_profile(pid), ctx).edges)
            for pid in PROFILES
        }
        if len({*paths.values()}) >= 2:
            divergent += 1
    assert divergent >= 1, "framework produced identical routes for every od/profile"


def test_safest_avoids_more_flood_than_cheapest():
    g = load_graph()
    ctx = _ctx(hour=18, rainfall=45.0)
    safest = shortest_route(g, "cubao", "pasay", resolve_profile("safest"), ctx)
    cheapest = shortest_route(g, "cubao", "pasay", resolve_profile("cheapest"), ctx)
    safe_flood = max((ctx.criteria[e.id].R for e in safest.edges), default=0)
    cheap_flood = max((ctx.criteria[e.id].R for e in cheapest.edges), default=0)
    assert safe_flood <= cheap_flood + 1e-9


# ----- api -----
def test_api_profiles():
    r = client.get("/api/profiles")
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()}
    assert ids == {"uncrowded", "cheapest", "safest", "convenient"}


def test_api_anchors():
    r = client.get("/api/anchors")
    assert r.status_code == 200
    assert len(r.json()) == 10


def test_api_route():
    r = client.post("/api/route", json={"origin": "cubao", "destination": "pasay",
                                        "profile": "safest", "hour": 8})
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["profile"]["id"] == "safest"
    assert set(body["criteria"]) == {"T", "F", "R", "P"}
    assert body["summary"]["fare_php"] > 0


def test_api_compare_returns_five():
    # 4 profiles + baseline
    r = client.post("/api/compare", json={"origin": "cubao", "destination": "pasay"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["routes"]) == 5
    ids = [x["profile"]["id"] for x in body["routes"]]
    assert "baseline" in ids


def test_api_route_has_exec_ms_and_discount():
    r = client.post("/api/route", json={"origin": "cubao", "destination": "pasay",
                                        "profile": "cheapest", "passenger_type": "student"})
    assert r.status_code == 200
    body = r.json()
    assert body["exec_ms"] >= 0
    # should be 20% off
    assert abs(body["summary"]["fare_discounted_php"] - body["summary"]["fare_php"] * 0.8) < 0.11


def test_api_unknown_profile_is_422():
    r = client.post("/api/route", json={"origin": "cubao", "destination": "pasay",
                                        "profile": "teleport"})
    assert r.status_code == 422
