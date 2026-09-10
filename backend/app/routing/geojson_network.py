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
#   - chains that never come near any anchor cannot serve an od pair, so they
#     are left out of the runtime graph (the file itself keeps everything)
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

_GEOJSON_PATH = Path(__file__).resolve().parent.parent / "data" / "virtual_stops.geojson"

LINK_RADIUS_KM = 0.3   # walking transfer distance stop <-> station
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


def build_jeepney_layer(anchors: dict[str, dict]) -> tuple[list[dict], list[dict], dict]:
    # returns (stop_nodes, edges, stats). anchors: id -> {lat, lng} from
    # anchors.json (the lrta-sourced coords stay authoritative).
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
    kept = dropped = links = 0
    counter = 0
    for key in sorted(chains, key=str):
        chain = sorted(chains[key], key=lambda t: t[0])
        # boarding links this chain can make (stop index -> anchor ids)
        chain_links = []
        for idx, (_, coords) in enumerate(chain):
            for aid, a in anchors.items():
                if _hav_km(coords, [a["lng"], a["lat"]]) <= LINK_RADIUS_KM:
                    chain_links.append((idx, aid))
        if not chain_links:
            dropped += 1
            continue  # unreachable from every station: cannot serve any od
        kept += 1
        route, category = key
        ids = []
        for dist_m, coords in chain:
            counter += 1
            nid = f"v_gj{counter}"
            ids.append(nid)
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
        for idx, aid in chain_links:
            links += 1
            edges.append({
                "from": aid, "to": ids[idx], "mode": "Jeepney",
                "fare": 0.0, "ridership": JEEPNEY_RIDERSHIP_BASELINE,
                "flood_risk": FLOOD_PLACEHOLDER,
                "distance_km": max(_hav_km(
                    [anchors[aid]["lng"], anchors[aid]["lat"]],
                    [stop_nodes[-len(chain) + idx]["lng"], stop_nodes[-len(chain) + idx]["lat"]]), 0.02),
            })

    stats = {"chains_kept": kept, "chains_dropped_unreachable": dropped,
             "stops": len(stop_nodes), "boarding_links": links}
    return stop_nodes, edges, stats
