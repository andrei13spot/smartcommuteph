import json
import math
import time
from pathlib import Path
import httpx  # already in requirements, no extra install needed

# Set automatic paths relative to backend/app/data/
DATA_DIR = Path(__file__).resolve().parent
INPUT_ANCHORS = DATA_DIR / "anchors.json"
INPUT_GRAPH = DATA_DIR / "graph.json"

OUTPUT_ANCHORS = DATA_DIR / "anchors_discretized.json"
OUTPUT_GRAPH = DATA_DIR / "graph_discretized.json"


def haversine_km(lat1, lng1, lat2, lng2):
    """Calculates distance in kilometers between two coordinates."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def get_street_route_geometry(lat1, lng1, lat2, lng2):
    """
    Auto-fetches the real street-level curve geometry from OSRM.
    Returns a list of [lat, lng] points following actual Metro Manila roads.
    """
    url = f"http://router.project-osrm.org/route/v1/driving/{lng1},{lat1};{lng2},{lat2}?geometries=geojson"
    try:
        response = httpx.get(url, timeout=10)
        data = response.json()
        if data.get("code") == "Ok":
            coords = data["routes"][0]["geometry"]["coordinates"]
            return [[pt[1], pt[0]] for pt in coords]
    except Exception as e:
        print(f"API Warning: {e}")
        
    # Fallback to straight line if API fails
    return [[lat1, lng1], [lat2, lng2]]


def extract_300m_street_stops(route_coords, interval_km=0.3):
    """
    Walks along the curved road geometry and drops virtual stops
    exactly every 300 meters on the road surface.
    """
    stops = []
    accumulated_dist = 0.0

    for i in range(len(route_coords) - 1):
        lat1, lng1 = route_coords[i]
        lat2, lng2 = route_coords[i + 1]

        seg_dist = haversine_km(lat1, lng1, lat2, lng2)

        while accumulated_dist + seg_dist >= interval_km:
            needed = interval_km - accumulated_dist
            t = needed / seg_dist if seg_dist > 0 else 0

            v_lat = lat1 + t * (lat2 - lat1)
            v_lng = lng1 + t * (lng2 - lng1)

            stops.append({"lat": round(v_lat, 6), "lng": round(v_lng, 6)})

            accumulated_dist = 0.0
            seg_dist -= needed
            lat1, lng1 = v_lat, v_lng

        accumulated_dist += seg_dist

    return stops


def generate_discretized_graph(interval_km=0.3):
    with open(INPUT_ANCHORS, "r", encoding="utf-8") as f:
        anchors_data = json.load(f)
    with open(INPUT_GRAPH, "r", encoding="utf-8") as f:
        graph_data = json.load(f)

    nodes = {a["id"]: a for a in anchors_data["anchors"]}
    discretized_anchors = list(anchors_data["anchors"])
    new_edges = []
    virtual_node_counter = 1

    print("Auto-fetching real street routes and generating 300m stops...")

    for edge in graph_data["edges"]:
        if edge["mode"] == "Jeepney":
            orig = nodes[edge["from"]]
            dest = nodes[edge["to"]]

            route_coords = get_street_route_geometry(
                orig["lat"], orig["lng"], dest["lat"], dest["lng"]
            )

            virtual_stops = extract_300m_street_stops(route_coords, interval_km)

            time.sleep(0.5)  # Rate limiting for OSRM

            if virtual_stops:
                prev_node_id = edge["from"]

                for i, stop_coords in enumerate(virtual_stops):
                    v_node_id = f"v_jeep_stop_{virtual_node_counter}"
                    virtual_node_counter += 1

                    discretized_anchors.append({
                        "id": v_node_id,
                        "name": f"Virtual Stop {virtual_node_counter - 1}",
                        "area": "Transit Route",
                        "lat": stop_coords["lat"],
                        "lng": stop_coords["lng"],
                        "lines": ["Jeepney"],
                        "source": "osrm street-snapped: 300m virtual stop"
                    })

                    new_edges.append({
                        "from": prev_node_id,
                        "to": v_node_id,
                        "mode": "Jeepney",
                        "fare": edge["fare"] if i == 0 else 0.0,
                        "ridership": edge["ridership"],
                        "flood_risk": edge["flood_risk"]
                    })
                    prev_node_id = v_node_id

                new_edges.append({
                    "from": prev_node_id,
                    "to": edge["to"],
                    "mode": "Jeepney",
                    "fare": 0.0,
                    "ridership": edge["ridership"],
                    "flood_risk": edge["flood_risk"]
                })
                continue

        new_edges.append(edge)

    # Save to separate discretized JSON files
    with open(OUTPUT_ANCHORS, "w", encoding="utf-8") as f:
        json.dump(
            {
                "description": "Street-snapped 300m discretized jeepney network.",
                "anchors": discretized_anchors,
            },
            f,
            indent=2,
        )

    with open(OUTPUT_GRAPH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "description": "Discretized jeepney edges.",
                "modes": graph_data["modes"],
                "edges": new_edges,
            },
            f,
            indent=2,
        )

    print(f"Success! Generated {virtual_node_counter - 1} street-guided virtual stops.")


if __name__ == "__main__":
    generate_discretized_graph()