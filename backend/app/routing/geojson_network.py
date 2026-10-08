# builds the jeepney layer from virtual_stops.geojson (princess's file, read
# only - this module never modifies it).
# the file holds 3,811 stop points on 155 real ltfrb jeepney routes, grouped
# into (route, category) chains ordered by cumulative distance_m (validated:
# all 161 chains strictly monotonic, median stop gap 0.30 km).
# graph construction, using only verifiable facts in the file:
#   - consecutive stops in a chain become jeepney edges with the REAL
#     along-road spacing (delta of distance_m)
#   - a stop within LINK_RADIUS_KM of an anchor gets a boarding link to it,
#     matching the paper's "intermodal transitions between virtual jeepney
#     nodes and nearby formal stations" (page 52)
#   - chains that never come near any anchor or rail/busway station cannot
#     serve an od pair, so they are left out of the runtime graph (the file
#     itself keeps everything)
#   - stops of different routes within TRANSFER_KM of each other get a "Walk"
#     link, so a rider can change jeepney lines there (graph.py also links
#     stops to nearby rail and busway stations the same way)
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

_GEOJSON_PATH = Path(__file__).resolve().parent.parent / "data" / "virtual_stops.geojson"

LINK_RADIUS_KM = 0.3   # walking transfer distance stop <-> station
TRANSFER_KM = 0.05     # stops of two jeepney routes this close share a corner: walk between them
# baseline crowding for jeepney edges (the geojson has no ridership field);
# same midpoint value the hand-set corridors used. documented assumption.
JEEPNEY_RIDERSHIP_BASELINE = 0.50
# placeholder only: the loader overrides flood risk with real mmda exposure
FLOOD_PLACEHOLDER = 0.05


def _hav_km(a: list[float], b: list[float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, [a[1], a[0], b[1], b[0]])
    x = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(x))


def available() -> bool:
    return _GEOJSON_PATH.exists()


def walk_edge(a: str, b: str, d_km: float) -> dict:
    # a walking transfer: no fare, no crowding (the loader adds the reverse)
    return {"from": a, "to": b, "mode": "Walk", "fare": 0.0, "ridership": 0.0,
            "flood_risk": FLOOD_PLACEHOLDER, "distance_km": max(d_km, 0.01)}


def build_jeepney_layer(anchors: dict[str, dict], stations: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
    # returns (stop_nodes, edges). anchors: id -> {lat, lng} from
    # anchors.json (the lrta-sourced coords stay authoritative). stations:
    # [{lat, lng}] of every rail and busway station, so a chain that only
    # meets a station (not an anchor) is kept too.
    with open(_GEOJSON_PATH, encoding="utf-8-sig") as fh:
        data = json.load(fh)

    chains: dict[tuple, list] = defaultdict(list)
    for f in data.get("features", []):
        p = f.get("properties", {})
        if p.get("type") == "anchor_point" or f.get("geometry", {}).get("type") != "Point":
            continue
        if p.get("distance_m") is None:
            continue
        chains[(p.get("route"), p.get("category"))].append(
            (float(p["distance_m"]), f["geometry"]["coordinates"]))

    stop_nodes: list[dict] = []
    edges: list[dict] = []
    stop_chain: dict[str, tuple] = {}
    counter = 0
    for key in sorted(chains, key=str):
        chain = sorted(chains[key], key=lambda t: t[0])
        # boarding links this chain can make (stop index -> anchor ids)
        chain_links = []
        for idx, (_, coords) in enumerate(chain):
            for aid, a in anchors.items():
                d = _hav_km(coords, [a["lng"], a["lat"]])
                if d <= LINK_RADIUS_KM:
                    chain_links.append((idx, aid, d))
        near_station = any(_hav_km(coords, [s["lng"], s["lat"]]) <= LINK_RADIUS_KM
                           for _, coords in chain for s in (stations or []))
        if not chain_links and not near_station:
            continue  # reaches no anchor and no station: cannot serve any od
        route, category = key
        ids = []
        for dist_m, coords in chain:
            counter += 1
            nid = f"v_gj{counter}"
            ids.append(nid)
            stop_chain[nid] = key
            stop_nodes.append({
                "id": nid,
                "name": f"Jeepney Stop ({route or 'route'})",
                "area": category or "Metro Manila",
                "lat": coords[1], "lng": coords[0],
                "lines": ["Jeepney"],
            })
        # chain edges with the real along-road spacing
        for i in range(len(chain) - 1):
            spacing_km = max((chain[i + 1][0] - chain[i][0]) / 1000.0, 0.02)
            edges.append({
                "from": ids[i], "to": ids[i + 1], "mode": "Jeepney",
                "fare": 0.0, "ridership": JEEPNEY_RIDERSHIP_BASELINE,
                "flood_risk": FLOOD_PLACEHOLDER, "distance_km": spacing_km,
            })
        # boarding links to nearby stations
        for idx, aid, d in chain_links:
            edges.append({
                "from": aid, "to": ids[idx], "mode": "Jeepney",
                "fare": 0.0, "ridership": JEEPNEY_RIDERSHIP_BASELINE,
                "flood_risk": FLOOD_PLACEHOLDER,
                "distance_km": max(d, 0.02),
            })

    # walking transfers between routes: for each stop, the nearest stop of every
    # other route within TRANSFER_KM (grid buckets keep this fast)
    cell = 0.0005
    grid: dict[tuple, list[dict]] = defaultdict(list)
    for s in stop_nodes:
        grid[(int(s["lat"] / cell), int(s["lng"] / cell))].append(s)
    linked: set[tuple] = set()
    for s in stop_nodes:
        cx, cy = int(s["lat"] / cell), int(s["lng"] / cell)
        best: dict[tuple, tuple] = {}
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for o in grid[(cx + dx, cy + dy)]:
                    if stop_chain[o["id"]] == stop_chain[s["id"]]:
                        continue
                    d = _hav_km([s["lng"], s["lat"]], [o["lng"], o["lat"]])
                    if d <= TRANSFER_KM and (stop_chain[o["id"]] not in best or d < best[stop_chain[o["id"]]][0]):
                        best[stop_chain[o["id"]]] = (d, o["id"])
        for d, oid in best.values():
            pair = tuple(sorted((s["id"], oid)))
            if pair not in linked:
                linked.add(pair)
                edges.append(walk_edge(pair[0], pair[1], d))

    return stop_nodes, edges
