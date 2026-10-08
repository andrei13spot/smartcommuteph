# threads the rail and edsa carousel corridor edges through their real
# stations (stations.json).
# a corridor like sm_north -> cubao on mrt-3 was one straight edge; with the
# station list it becomes north ave -> quezon -> kamuning -> cubao with real
# coordinates, so the map follows the actual line, leg km is station-accurate,
# and the official fare matrices can price a leg by its board/alight stations.
# station nodes are pass-through (virtual): they never appear in the dropdowns
# and riding through them on the same train adds no transfer.
from __future__ import annotations

import json
from pathlib import Path

from .graph import haversine_km

_STATIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "stations.json"
_MATCH_RADIUS_KM = 1.0  # an anchor must sit within this of a station to snap to it; a station away from its hub gets its own node (below), so the hub reaches it by that link (sm north mall is 0.64 km from north ave mrt)
# the carousel has no stop at cubao or shaw; those anchors board at main ave
# (0.9 km) and ortigas (0.8 km), so the busway snaps within a wider radius
_MATCH_RADIUS_BY_MODE: dict[str, float] = {}
_OWN_NODE_KM = 0.15  # a station further than this from its hub gets its own node


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

    def nearest_station(line_stations, anchor, mode):
        best_i, best_d = None, _MATCH_RADIUS_BY_MODE.get(mode, _MATCH_RADIUS_KM)
        for i, s in enumerate(line_stations):
            d = haversine_km(anchor["lat"], anchor["lng"], s["lat"], s["lng"])
            if d < best_d:
                best_i, best_d = i, d
        return best_i

    for e in raw_edges:
        line = lines.get(e["mode"])
        a, b = anchor_pos.get(e["from"]), anchor_pos.get(e["to"])
        if not line or a is None or b is None:
            new_edges.append(e)
            continue
        ia = nearest_station(line["stations"], a, e["mode"])
        ib = nearest_station(line["stations"], b, e["mode"])
        if ia is None or ib is None or ia == ib:
            new_edges.append(e)  # an end is off this line: keep the direct edge
            continue
        step = 1 if ib > ia else -1
        between = line["stations"][ia + step:ib:step]  # strictly between the ends
        # an anchor is one hub point shared by several lines (cubao gateway sits
        # on the lrt-2 araneta center-cubao station; the mrt-3 cubao station is
        # 435 m away on edsa). when the line's own station is further than
        # _OWN_NODE_KM from the hub it gets its own node at its real position,
        # so the line is drawn and measured from the real station and the hub
        # is reached by that short link
        own_a = haversine_km(a["lat"], a["lng"], line["stations"][ia]["lat"], line["stations"][ia]["lng"]) > _OWN_NODE_KM
        own_b = haversine_km(b["lat"], b["lng"], line["stations"][ib]["lat"], line["stations"][ib]["lng"]) > _OWN_NODE_KM
        if own_a:
            between = [line["stations"][ia], *between]
        if own_b:
            between = [*between, line["stations"][ib]]
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
        for k, (u, v) in enumerate(zip(hops, hops[1:])):
            # the hop between a hub and its own station node is the walk to the
            # platform, not a ride: no fare, no crowding, no transfer. it keeps
            # the line's speed for its time (speed_mode), so the route times do
            # not change; before, a route could "ride" only this hop and pay a
            # whole bus fare for it (monumento circle -> monumento busway stop)
            if (k == 0 and own_a) or (k == len(hops) - 2 and own_b):
                new_edges.append({**e, "from": u, "to": v, "distance_km": None, "mode": "Walk",
                                  "speed_mode": e["mode"], "fare": 0.0, "ridership": 0.0})
            else:
                new_edges.append({**e, "from": u, "to": v, "distance_km": None})

    return list(station_nodes.values()), new_edges
