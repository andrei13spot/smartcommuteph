import polyline
import pyproj
from shapely.geometry import LineString
from shapely.ops import transform
import json

# 1. Load the grouped transit routes
with open("jeepney_polylines.json", "r") as file:
    grouped_routes = json.load(file)

# 2. Load the anchor points
with open("anchors.json", "r") as file:
    anchors_data = json.load(file)

# --- PROJECTION SETUP ---
project_to_meters = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True).transform
project_to_gps = pyproj.Transformer.from_crs("EPSG:32651", "EPSG:4326", always_xy=True).transform

features = []
total_stops = 0

# A visually distinct color palette for the routes
ROUTE_COLORS = [
    "#E6194B", "#3CB44B", "#FFE119", "#4363D8", "#F58231",
    "#911EB4", "#46F0F0", "#F032E6", "#BCF60C", "#FABEBE",
    "#008080", "#E6BEFF", "#9A6324", "#FFFAC8", "#800000",
    "#AAFFC3", "#808000", "#FFD8B1", "#000075", "#808080"
]

# --- ADD ANCHOR POINTS TO GEOJSON ---
for anchor in anchors_data["anchors"]:
    features.append({
        "type": "Feature",
        "properties": {
            "type": "anchor_point",
            "id": anchor["id"],
            "name": anchor["name"],
            "area": anchor["area"],
            "lines": anchor["lines"],
            "marker-color": "#000000" # Making anchors black so they stand out
        },
        "geometry": {
            "type": "Point",
            "coordinates": [anchor["lng"], anchor["lat"]]
        }
    })

# --- PROCESS EXACT ROUTES AND VIRTUAL STOPS ---
route_index = 0 # Counter to keep track of colors across all categories

# LOOP 1: Iterate through each location category (e.g., "Antipolo to Doroteo")
for location_category, routes_dict in grouped_routes.items():
    
    # LOOP 2: Iterate through the exact route names within that category
    for route_name, encoded_polyline in routes_dict.items():
        
        # Pick a unique color based on the overall route index
        current_color = ROUTE_COLORS[route_index % len(ROUTE_COLORS)]
        
        # Decode the polyline into coordinates
        coordinates = polyline.decode(encoded_polyline)
        lon_lat_coords = [[lon, lat] for lat, lon in coordinates]
        
        # A. Save the exact route shape as a LineString Feature
        features.append({
            "type": "Feature",
            "properties": {
                "name": route_name,
                "route": route_name,
                "category": location_category, 
                "type": "exact_route_path",
                "stroke": current_color, 
                "stroke-width": 4
            },
            "geometry": {
                "type": "LineString",
                "coordinates": lon_lat_coords
            }
        })

        # B. Generate the 300m virtual stops
        route_line = LineString(lon_lat_coords)
        route_line_meters = transform(project_to_meters, route_line)

        distance_covered = 0
        while distance_covered < route_line_meters.length:
            stop_point_meters = route_line_meters.interpolate(distance_covered)
            stop_point_gps = transform(project_to_gps, stop_point_meters)
            
            features.append({
                "type": "Feature",
                "properties": {
                    "route": route_name,
                    "category": location_category,
                    "type": "virtual_stop",
                    "distance_m": round(distance_covered, 2),
                    "marker-color": current_color # Colors the points to match the route line
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(stop_point_gps.x, 6), round(stop_point_gps.y, 6)]
                }
            })
            distance_covered += 300
            total_stops += 1
            
        # Increment the index so the next route gets a new color
        route_index += 1

# Compile everything into a valid GeoJSON FeatureCollection
geojson_output = {
    "type": "FeatureCollection",
    "features": features
}

filename = "SmartCommute_Exact.geojson"
with open(filename, 'w', encoding='utf-8') as f:
    json.dump(geojson_output, f, indent=4)

# --- UPDATED PRINT STATEMENTS ---
print(f"[!] Success! Processed {len(anchors_data['anchors'])} anchor points, {route_index} routes, and {total_stops} virtual stops.")
print(f"[!] Data successfully saved into: '{filename}'")