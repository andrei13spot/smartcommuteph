# directed transit graph g = (v, e).
# edges are stored one way in the json, we add the reverse so it's bidirectional.
# haversine distance is used for edge length and for the a* heuristic.
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent / "data"
_ML_DATA = Path(__file__).resolve().parent.parent / "ml" / "data"

# flood exposure from the mmda incident points: an incident within this radius
# of an edge contributes risk, scaled by its flood depth and closeness
_FLOOD_RADIUS_KM = 0.5
_FLOOD_DEPTH_REF_IN = 24.0   # ~2ft of water = fully risky
_FLOOD_BASELINE = 0.05       # edges with no incident history = low-risk baseline

# per-mode operating speeds in km/h. used to get base travel time = distance / speed.
MODE_SPEED_KMH = {
    "LRT-1": 40.0,
    "LRT-2": 40.0,
    "MRT-3": 60.0,
    "EDSA-Bus": 30.0,
    "Jeepney": 20.0,
}

# fastest speed, only used in the heuristic so it stays admissible
MAX_SPEED_KMH = max(MODE_SPEED_KMH.values())


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    # great-circle distance between two points in km
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class Node:
    id: str
    name: str
    area: str
    lat: float
    lng: float
    lines: tuple[str, ...]
    virtual: bool = False  # true for the 300m jeepney stops, they are not od anchors


@dataclass(frozen=True)
class Edge:
    id: str
    src: str
    dst: str
    mode: str
    base_time: float      # minutes
    fare: float           # php
    ridership: float      # raw 0..1 baseline
    flood_risk: float     # raw 0..1 baseline
    distance_km: float


@dataclass
class Graph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: dict[str, Edge] = field(default_factory=dict)
    adjacency: dict[str, list[Edge]] = field(default_factory=dict)

    def neighbors(self, node_id: str) -> list[Edge]:
        return self.adjacency.get(node_id, [])

    def node(self, node_id: str) -> Node:
        return self.nodes[node_id]

    def straight_line_km(self, a: str, b: str) -> float:
        na, nb = self.nodes[a], self.nodes[b]
        return haversine_km(na.lat, na.lng, nb.lat, nb.lng)

    @property
    def real_nodes(self) -> dict[str, Node]:
        # the 10 od anchors only, virtual jeepney stops excluded. the benchmark
        # and the dropdowns use these so od pairs stay c(10,2) = 45
        return {i: n for i, n in self.nodes.items() if not n.virtual}


def _load_json(name: str) -> dict:
    with open(_DATA / name, encoding="utf-8") as fh:
        return json.load(fh)


def _point_to_segment_km(plat: float, plng: float,
                         alat: float, alng: float,
                         blat: float, blng: float) -> float:
    # distance from an incident point to an edge segment. equirectangular
    # projection is fine at city scale (errors < 1m over a few km)
    kx = 111.32 * math.cos(math.radians(plat))  # km per degree lng here
    ky = 110.57                                  # km per degree lat
    ax, ay = (alng - plng) * kx, (alat - plat) * ky
    bx, by = (blng - plng) * kx, (blat - plat) * ky
    dx, dy = bx - ax, by - ay
    seg_len2 = dx * dx + dy * dy
    if seg_len2 == 0:
        return math.hypot(ax, ay)
    t = max(0.0, min(1.0, -(ax * dx + ay * dy) / seg_len2))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(cx, cy)


def _load_flood_incidents() -> list[dict]:
    path = _ML_DATA / "mmda_flood_incidents.json"
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        incidents = data["incidents"]
        return [i for i in incidents
                if isinstance(i, dict) and "lat" in i and "lng" in i and "depth_in" in i]
    except Exception:
        return []  # unusable file = behave like no incident data


def _flood_exposure(graph: "Graph") -> None:
    # replace each edge's flood_risk with real exposure from the mmda incident
    # points (per the paper: per-segment historical flood record; segments with
    # no record stay as low-risk baseline cases). depth and closeness both scale
    # the contribution; overlapping incidents accumulate and cap at 1.
    incidents = _load_flood_incidents()
    if not incidents:
        return  # keep the static json values if the incident file is missing
    for eid, e in list(graph.edges.items()):
        a, b = graph.nodes[e.src], graph.nodes[e.dst]
        exposure = 0.0
        for i in incidents:
            d = _point_to_segment_km(i["lat"], i["lng"], a.lat, a.lng, b.lat, b.lng)
            if d >= _FLOOD_RADIUS_KM:
                continue
            depth = min(i["depth_in"] / _FLOOD_DEPTH_REF_IN, 1.0)
            exposure += depth * (1.0 - d / _FLOOD_RADIUS_KM)
        risk = max(_FLOOD_BASELINE, min(1.0, exposure))
        graph.edges[eid] = Edge(
            id=e.id, src=e.src, dst=e.dst, mode=e.mode, base_time=e.base_time,
            fare=e.fare, ridership=e.ridership, flood_risk=risk,
            distance_km=e.distance_km,
        )
    # adjacency holds the same edge objects, rebuild it from the updated ones
    for node_id in graph.adjacency:
        graph.adjacency[node_id] = []
    for e in graph.edges.values():
        graph.adjacency[e.src].append(e)


def _use_dense() -> bool:
    # the discretized graph (300m jeepney stops from split_jeepneys.py) is the
    # default when its files exist. set SCPH_DENSE_GRAPH=0 to force the coarse
    # 10-node graph, e.g. for quick debugging.
    import os
    if os.getenv("SCPH_DENSE_GRAPH", "1") == "0":
        return False
    return (_DATA / "anchors_discretized.json").exists() and (_DATA / "graph_discretized.json").exists()


@lru_cache(maxsize=1)
def load_graph() -> Graph:
    # build the graph once and keep it cached
    if _use_dense():
        anchors = _load_json("anchors_discretized.json")["anchors"]
        raw_edges = _load_json("graph_discretized.json")["edges"]
    else:
        anchors = _load_json("anchors.json")["anchors"]
        raw_edges = _load_json("graph.json")["edges"]

    graph = Graph()
    for a in anchors:
        graph.nodes[a["id"]] = Node(
            id=a["id"], name=a["name"], area=a["area"],
            lat=a["lat"], lng=a["lng"], lines=tuple(a["lines"]),
            virtual=a["id"].startswith("v_"),
        )
        graph.adjacency[a["id"]] = []

    def add_edge(src: str, dst: str, mode: str, e: dict) -> None:
        dist = graph.straight_line_km(src, dst)
        # time = distance / mode speed, in minutes
        speed = MODE_SPEED_KMH.get(mode, MAX_SPEED_KMH)
        base_time = dist / speed * 60.0
        edge = Edge(
            id=f"{src}->{dst}:{mode}",
            src=src, dst=dst, mode=mode,
            base_time=base_time, fare=float(e["fare"]),
            ridership=float(e["ridership"]), flood_risk=float(e["flood_risk"]),
            distance_km=dist,
        )
        graph.edges[edge.id] = edge
        graph.adjacency[src].append(edge)

    for e in raw_edges:
        add_edge(e["from"], e["to"], e["mode"], e)
        add_edge(e["to"], e["from"], e["mode"], e)  # reverse direction

    # swap the synthetic flood_risk baselines for real mmda incident exposure
    _flood_exposure(graph)

    return graph
