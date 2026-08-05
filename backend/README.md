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
| GET  | `/api/status`   | Graph size, ML model state, rainfall source |
| GET  | `/api/profiles` | The four AHP profiles + weights |
| GET  | `/api/anchors`  | The ten transit anchor points (dropdowns) |
| GET  | `/api/network`  | All nodes + edges incl. virtual jeepney stops |
| POST | `/api/route`    | One route for a profile + OD pair |
| POST | `/api/compare`  | Same OD under 4 profiles + baseline (5 results) |
| GET  | `/api/benchmark` | SOP1–SOP3 statistics (t-tests, Jaccard, RM-ANOVA) |
| GET  | `/api/benchmark/log` | The 360-row × 8-KPI log (`?format=csv`) |
| GET  | `/api/ml-metrics` | RMSE/MAE for the LSTM and RFR |
| POST | `/api/inspect`  | Per-edge cost decomposition for one query |

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

Both models are **trained** on real data:

- **LSTM ridership** (`ml/ridership.py`, trained by `ml/train_ridership.py`) —
  DOTC-MRT3 hourly ridership reports 2024–2025 (~1,175 hourly observations),
  24-hour window, chronological 70-15-15 split with early stopping at the
  validation-loss minimum. Ships trained; without TensorFlow the engine falls
  back to the data-derived mean hourly curve.
- **RFR flood risk** (`ml/flood.py`, trained by `ml/train_flood.py`) — features
  are rainfall, mode sensitivity, and per-edge exposure computed from **101
  real MMDA flood incidents** (`ml/data/mmda_flood_incidents.json`). The
  `.joblib` is gitignored: regenerate once with `python -m app.ml.train_flood`.

Rainfall comes from the **PAGASA TenDay Forecast API** when `SCPH_PAGASA_TOKEN`
is set (see `docs/pagasa-api-request.md`); otherwise an offline 8 mm default is
used and `/api/status` reports the source.

Env vars: `SCPH_DENSE_GRAPH=0` forces the coarse 10-node graph (default is the
264-node discretized graph when its files exist); `SCPH_PAGASA_TOKEN` enables
the live rainfall feed; `SCPH_CORS_ORIGINS` overrides allowed origins.

> Research prototype — not a deployed transit application.
> Group 11 · BSCS · CCIS · Polytechnic University of the Philippines · 2026
