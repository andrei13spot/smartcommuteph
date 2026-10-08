# builds walk_paths.json: the street path for each anchor's walk link to its
# own station platform (the links rail_stations.py adds when a station sits
# 0.15 to 1 km from its anchor). the gateway draws these instead of a straight
# line through buildings. paths come from the openstreetmap foot router
# (routing.openstreetmap.de, osrm foot profile) and are saved here, so the
# app never calls the service at run time.
# usage, with the engine running on 8000: python app/data/build_walk_paths.py [engine url]
import json
import sys
import time
import urllib.request
from pathlib import Path

ENGINE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
GATEWAY_RULE_MIN_KM, GATEWAY_RULE_MAX_KM = 0.15, 1.0
HERE = Path(__file__).parent
ROUTER = "https://routing.openstreetmap.de/routed-foot/route/v1/foot/{a};{b}?overview=full&geometries=geojson"


def km(a, b):
    import math
    r = math.radians
    h = math.sin(r(b["lat"] - a["lat"]) / 2) ** 2 + math.cos(r(a["lat"])) * math.cos(r(b["lat"])) * math.sin(r(b["lng"] - a["lng"]) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "smartcommuteph-thesis/1.0"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def main():
    lines = json.loads((HERE / "stations.json").read_text(encoding="utf-8"))["lines"]
    net = get(f"{ENGINE}/api/network")
    nodes = {n["id"]: n for n in net["nodes"]}
    links, seen = [], set()
    for e in net["edges"]:
        a, b = nodes.get(e["from_id"]), nodes.get(e["to_id"])
        if not a or not b or e["mode"] not in lines:
            continue
        if a["id"].startswith("v_") == b["id"].startswith("v_"):
            continue
        anchor, station = (a, b) if not a["id"].startswith("v_") else (b, a)
        near = min(lines[e["mode"]]["stations"], key=lambda s: km(anchor, s))
        d = km(anchor, near)
        if not (GATEWAY_RULE_MIN_KM < d <= GATEWAY_RULE_MAX_KM) or near["name"] != station["name"]:
            continue
        key = (anchor["id"], e["mode"], station["name"])
        if key in seen:
            continue
        seen.add(key)
        r = get(ROUTER.format(a=f'{anchor["lng"]},{anchor["lat"]}', b=f'{station["lng"]},{station["lat"]}'))
        route = r["routes"][0]
        links.append({
            "anchor_id": anchor["id"], "anchor": anchor["name"], "mode": e["mode"], "station": station["name"],
            "straight_km": round(d, 3), "walk_km": round(route["distance"] / 1000, 3),
            "walk_min": round(route["duration"] / 60, 1),
            "points": [[round(lat, 6), round(lng, 6)] for lng, lat in route["geometry"]["coordinates"]],
        })
        print(f'{anchor["name"]} -> {station["name"]} ({e["mode"]}): straight {d:.2f} km, walk {route["distance"] / 1000:.2f} km')
        time.sleep(1)
    out = {
        "description": "street walking paths from an anchor to its own station platform, drawn by the gateway "
                       "instead of a straight line. built by build_walk_paths.py from the openstreetmap foot "
                       "router (routing.openstreetmap.de, osrm foot profile, openstreetmap contributors). "
                       "points are [lat, lng], anchor first.",
        "links": links,
    }
    (HERE / "walk_paths.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(len(links), "links saved")


if __name__ == "__main__":
    main()
