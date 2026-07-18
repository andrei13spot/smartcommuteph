# api contract — smartcommute ph

owner: andrei. locked with luis before any wiring. dave tests against this.
base url: the node gateway (`http://127.0.0.1:8080`). the python engine sits behind it.

## anchor ids

`monumento, sm_novaliches, sm_north, cubao, doroteo_jose, shaw, antipolo, pasig, pasay, pitx`

## profiles

`uncrowded | cheapest | safest | convenient` — plus `baseline` (distance-based a*, only shows up in /compare and the benchmark).

---

## POST /route

one route for one profile.

request:
```json
{
  "origin": "cubao",
  "destination": "pasay",
  "profile": "safest",
  "passenger_type": "student"
}
```
- `origin`, `destination`, `profile` — required
- `origin != destination` — else 400
- `passenger_type` — optional, `regular | student | senior`. student/senior gets 20% off the fare kpi
- optional: `hour` (0–23, ridership context), `rainfall_mm` (flood context)

response:
```json
{
  "profile": "safest",
  "origin": "cubao",
  "destination": "pasay",
  "geometry": [[14.6199, 121.051], [14.5818, 121.0535], [14.5378, 120.9967]],
  "kpis": {
    "travel_time_min": 12.1,
    "distance_km": 10.4,
    "fare_php": 40.0,
    "transfers": 0,
    "flood_risk_score": 0.03,
    "ridership_density_score": 0.42,
    "nodes_expanded": 3,
    "exec_ms": 0.05
  },
  "why_this_route": { "heading": "...", "description": "..." },
  "criteria": { "T": 0.42, "F": 0.48, "R": 0.03, "P": 0.0 }
}
```

the 8 kpis (same order as the benchmark log):
1. `travel_time_min` — in-vehicle time + transfer friction
2. `distance_km`
3. `fare_php` — 20% student/senior discount already applied when passenger_type is set
4. `transfers` — mode switches
5. `flood_risk_score` — normalized 0..1, worst segment
6. `ridership_density_score` — normalized 0..1, average
7. `nodes_expanded` — a* states popped (pruning evidence)
8. `exec_ms` — a* run time

errors: `400` bad input (missing field / same od), `422` unknown profile or anchor id, `502` engine down.

---

## POST /compare

same od, all 4 profiles **plus baseline** = 5 results.

request:
```json
{ "origin": "cubao", "destination": "pasay" }
```
- `origin`, `destination` required, cannot be the same
- optional: `hour`, `rainfall_mm`, `passenger_type`

response:
```json
{
  "origin": "cubao",
  "destination": "pasay",
  "results": [
    { "profile": "uncrowded", "geometry": [...], "kpis": {...}, "why_this_route": {...}, "criteria": {...} },
    { "profile": "cheapest", ... },
    { "profile": "safest", ... },
    { "profile": "convenient", ... },
    { "profile": "baseline", ... }
  ]
}
```

same result shape as /route, five of them. baseline is always last.

---

## benchmark log

45 od pairs x 4 profiles x 2 algorithms = **360 rows**.
columns: `od_pair, profile, algorithm` + the 8 kpis above, same names.

---

## other endpoints (internal / dashboards)

- `GET /api/map/anchors` — the 10 anchors with coords
- `GET /api/map/network` — whole graph as geojson (maps)
- `POST /api/map/route`, `POST /api/map/compare` — geojson versions for leaflet
- `GET /api/benchmark`, `GET /api/ml-metrics`, `POST /api/inspect` — researcher console
- `GET /healthz` — gateway + engine health
