import json
import math
import os

# We will borrow Andrei's Haversine formula to calculate distance in km
def haversine_km(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))

def split_jeepney_routes(anchors_file, graph_file, interval_km=0.3):
    with open(anchors_file, 'r', encoding='utf-8') as f:
        anchors_data = json.load(f)
    with open(graph_file, 'r', encoding='utf-8') as f:
        graph_data = json.load(f)

    # Convert anchors list to a dictionary for easy coordinate lookup
    nodes = {a["id"]: a for a in anchors_data["anchors"]}
    
    new_edges = []
    virtual_node_counter = 1

    for edge in graph_data["edges"]:
        if edge["mode"] == "Jeepney":
            orig = nodes[edge["from"]]
            dest = nodes[edge["to"]]
            
            # Calculate total distance
            total_dist = haversine_km(orig["lat"], orig["lng"], dest["lat"], dest["lng"])
            
            if total_dist > interval_km:
                num_segments = int(total_dist // interval_km)
                
                prev_node_id = edge["from"]
                
                for i in range(num_segments):
                    # Linear interpolation for latitude and longitude
                    t = ((i + 1) * interval_km) / total_dist
                    v_lat = orig["lat"] + t * (dest["lat"] - orig["lat"])
                    v_lng = orig["lng"] + t * (dest["lng"] - orig["lng"])
                    
                    # Create the new virtual anchor point
                    v_node_id = f"v_jeep_stop_{virtual_node_counter}"
                    virtual_node_counter += 1
                    
                    anchors_data["anchors"].append({
                        "id": v_node_id,
                        "name": f"Virtual Stop {virtual_node_counter - 1}",
                        "area": "Transit Route",
                        "lat": round(v_lat, 6),
                        "lng": round(v_lng, 6),
                        "lines": ["Jeepney"]
                    })
                    
                    # Create the short edge.
                    # Only the first segment gets the base fare. The rest are 0.
                    new_edges.append({
                        "from": prev_node_id,
                        "to": v_node_id,
                        "mode": "Jeepney",
                        "fare": edge["fare"] if i == 0 else 0,
                        "ridership": edge["ridership"],
                        "flood_risk": edge["flood_risk"]
                    })
                    prev_node_id = v_node_id
                
                # Connect the final virtual stop to the actual destination
                new_edges.append({
                    "from": prev_node_id,
                    "to": edge["to"],
                    "mode": "Jeepney",
                    "fare": 0,
                    "ridership": edge["ridership"],
                    "flood_risk": edge["flood_risk"]
                })
                continue # Skip adding the original unbroken edge
                
        # If it's not a jeepney or it's shorter than 300m, keep the edge as is
        new_edges.append(edge)

    # Save the updated files
    graph_data["edges"] = new_edges
    
    with open('anchors_updated.json', 'w', encoding='utf-8') as f:
        json.dump(anchors_data, f, indent=2)
    with open('graph_updated.json', 'w', encoding='utf-8') as f:
        json.dump(graph_data, f, indent=2)
        
    print("Success! Replaced files generated.")

# Run the function
split_jeepney_routes('anchors.json', 'graph.json')