# threads the rail corridor edges through the real stations (stations.json).
# a corridor like sm_north -> cubao on mrt-3 was one straight edge; with the
# station list it becomes north ave -> quezon -> kamuning -> cubao with real
# coordinates, so the map follows the actual line, leg km is station-accurate,
# and the official fare matrices can price a leg by its board/alight stations.
# station nodes are pass-through (virtual): they never appear in the dropdowns
# and riding through them on the same train adds no transfer.
from __future__ import annotations

import json
import math
from pathlib import Path

_STATIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "stations.json"
_MATCH_RADIUS_KM = 0.6  # an anchor must sit within this of a station to snap to it


def _hav_km(lat1, lng1, lat2, lng2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def _load_lines() -> dict:
    try:
        return json.loads(_STATIONS_PATH.read_text(encoding="utf-8"))["lines"]
    except Exception:
        return {}


def subdivide_rail(anchors: list[dict], raw_edges: list[dict]) -> tuple[list[dict], list[dict]]:
    # returns (station_nodes_to_add, new_edge_list). rail edges whose two
    # anchors both snap onto the same line's station sequence get replaced by
    # the station-by-station chain; everything else passes through unchanged.
    lines = _load_lines()
    if not lines:
        return [], raw_edges

    anchor_pos = {a["id"]: a for a in anchors}
    new_edges: list[dict] = []
    station_nodes: dict[str, dict] = {}
    counter = 0

    def nearest_station(line_stations, anchor):
        best_i, best_d = None, _MATCH_RADIUS_KM
        for i, s in enumerate(line_stations):
            d = _hav_km(anchor["lat"], anchor["lng"], s["lat"], s["lng"])
            if d < best_d:
                best_i, best_d = i, d
        return best_i

    for e in raw_edges:
        line = lines.get(e["mode"])
        a, b = anchor_pos.get(e["from"]), anchor_pos.get(e["to"])
        if not line or a is None or b is None:
            new_edges.append(e)
            continue
        ia = nearest_station(line["stations"], a)
        ib = nearest_station(line["stations"], b)
        if ia is None or ib is None or ia == ib:
            new_edges.append(e)  # an end is off this line: keep the direct edge
            continue
        step = 1 if ib > ia else -1
        between = line["stations"][ia + step:ib:step]  # strictly between the ends
        if not between:
            new_edges.append(e)
            continue
        chain_ids = []
        for s in between:
            key = f'{e["mode"]}::{s["name"]}'
            if key not in station_nodes:
                counter += 1
                station_nodes[key] = {
                    "id": f"v_st_{e['mode'].lower().replace('-', '')}_{counter}",
                    "name": s["name"], "area": "Station",
                    "lat": s["lat"], "lng": s["lng"], "lines": [e["mode"]],
                }
            chain_ids.append(station_nodes[key]["id"])
        hops = [e["from"], *chain_ids, e["to"]]
        for u, v in zip(hops, hops[1:]):
            new_edges.append({**e, "from": u, "to": v, "distance_km": None})

    return list(station_nodes.values()), new_edges
