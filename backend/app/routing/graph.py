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


def _load_json(name: str) -> dict:
    with open(_DATA / name, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def load_graph() -> Graph:
    # build the graph once and keep it cached
    anchors = _load_json("anchors.json")["anchors"]
    raw_edges = _load_json("graph.json")["edges"]

    graph = Graph()
    for a in anchors:
        graph.nodes[a["id"]] = Node(
            id=a["id"], name=a["name"], area=a["area"],
            lat=a["lat"], lng=a["lng"], lines=tuple(a["lines"]),
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

    return graph
