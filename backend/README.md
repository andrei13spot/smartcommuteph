# SmartCommute PH — Commuter Routing API

Reference implementation (backend) of the SmartCommute PH routing **framework**:
AHP-derived profile weights + ML-predicted edge values (LSTM ridership, RFR
flood risk) inside a **constraint-aware A\*** over the Cubao-quadrant transit
graph. This is the validation instrument behind the commuter-facing mockups
(`profiles → location → result → compare`).

## Quick start

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open the interactive docs at <http://127.0.0.1:8000/docs>.

Run the tests:

```bash
pytest -q
```

## The cost function

Every edge is scored with the framework's multi-criteria cost:

```
Cost(e) = Time(e) × (1 + w_T·T' + w_F·F' + w_R·R' + w_P·P')
```

- `Time(e)` — base travel time (minutes).
- `T', F', R', P'` — Min-Max normalized values in `[0,1]` for the four secondary
  criteria: **ridership**, **fare**, **flood risk**, **transfer friction**.
- `w_*` — AHP weights for the active profile (sum to 1).

`A*` uses `f(n) = g(n) + h(n)` where `h(n) = straight_line_distance / 60 km/h`
(admissible, consistent). Because the transfer term `P'` depends on the mode a
node was reached by, search state is `(node, arriving_mode)`.

## Profiles

| Profile | Dominant criterion | Weight | Theme |
|---|---|---|---|
| Uncrowded  | Ridership `T` | 0.55 | blue |
| Cheapest   | Fare `F`      | 0.55 | yellow |
| Safest     | Flood risk `R`| 0.55 | red |
| Convenient | Transfer `P`  | 0.55 | green |

Non-dominant criteria get 0.15 each.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET  | `/api/health`   | Liveness check |
| GET  | `/api/profiles` | The four AHP profiles + weights |
| GET  | `/api/anchors`  | The ten transit anchor points |
| POST | `/api/route`    | One route for a profile + OD pair |
| POST | `/api/compare`  | Same OD under all four profiles |

`POST /api/route` body:

```json
{ "origin": "cubao", "destination": "pasay", "profile": "safest",
  "hour": 18, "rainfall_mm": 45 }
```

`hour` (ridership context) and `rainfall_mm` (flood context) are optional; they
default to the server clock and the live PAGASA value. Anchor ids match the
`<select>` values in the frontend `location.html`.

## Layout

```
app/
  main.py              FastAPI app + CORS + lifespan
  config.py            settings (CORS origins, metadata)
  schemas.py           Pydantic request/response models
  profiles.py          AHP profiles + weight vectors
  data/
    anchors.json       10 transit anchor points
    graph.json         seed transit edges (Cubao quadrant)
  routing/
    graph.py           graph model + haversine + loader
    cost.py            5×5 friction matrix, Min-Max norm, edge cost
    heuristic.py       admissible time heuristic
    astar.py           constraint-aware multi-criteria A*
  ml/
    ridership.py       LSTM placeholder (time-of-day demand curve)
    flood.py           RFR placeholder + PAGASA rainfall hook
  services/
    router_service.py  orchestration + result aggregation
  api/
    routes.py          endpoint handlers
tests/
  test_routing.py      engine + API tests
```

## ML components — current status

`ml/ridership.py` and `ml/flood.py` are **placeholders** with the final
interfaces wired in. They modulate the seed baselines (time-of-day demand for
ridership; rainfall sensitivity by mode for flood) so the full pipeline —
normalization, cost function, A\*, aggregation — runs end to end today. Drop in
the trained LSTM / RFR models and the live PAGASA TenDay Forecast call without
changing any caller: the contracts are `predict(edge, hour) → [0,1]` and
`predict(edge, rainfall_mm) → [0,1]`.

> Research prototype — not a deployed transit application.
> Group 11 · BSCS · CCIS · Polytechnic University of the Philippines · 2026
