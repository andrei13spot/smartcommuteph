# SmartCommute PH — Gateway (Node.js)

The **Node half** of the stack. An Express server that:

1. **Serves the static frontend** (`index/profiles/location/result/compare/about/dashboard/researcher` + `styles.css`, `script.js`, `map.js`, `researcher-script.js`, `researcher-style.css`) from the repo root.
2. **Exposes the map API** under `/api/map/*`, turning the Python routing
   engine's output into **GeoJSON** the Leaflet frontend draws directly.
3. **Proxies** routing/profile calls to the Python FastAPI engine, so the
   browser only ever talks to one same-origin server (no CORS).

```
browser ──> Node gateway (:8080)  ──>  Python engine (:8000)
            static files                routing + ML (A*, AHP, LSTM, RFR)
            /api/map/*  (GeoJSON)
```

## Run

The gateway needs the Python engine running first (see `../backend/README.md`):

```bash
# terminal 1 — Python routing engine
cd backend
uvicorn app.main:app --port 8000

# terminal 2 — Node gateway + frontend
cd gateway
npm install
npm start            # http://127.0.0.1:8080
```

Open <http://127.0.0.1:8080/> (or `/index.html`). The landing page draws the
transit network; `result.html` draws the computed route for the saved trip.

### Config

| Env var | Default | Purpose |
|---|---|---|
| `PORT` | `8080` | Gateway port |
| `PYTHON_API_URL` | `http://127.0.0.1:8000` | Where the routing engine lives |

## API

| Method | Path | Returns |
|---|---|---|
| POST | `/route`           | Contract shape (`kpis`, `why_this_route`, `criteria`, `geometry`) for one profile + OD pair; see `../docs/api-contract.md` |
| POST | `/compare`         | `{ origin, destination, results }` with five contract results (four profiles + baseline) |
| GET  | `/api/map/network` | GeoJSON of all stations + mode-colored edges |
| POST | `/api/map/route`   | `{ route, geojson }` for one profile + OD pair |
| POST | `/api/map/compare` | Four routes (one per profile), each with geojson |
| GET  | `/api/map/anchors` | Pass-through: the ten anchor points |
| GET  | `/api/map/profiles`| Pass-through: the four AHP profiles |
| GET  | `/api/status`      | Pass-through: graph size, ML model state, rainfall source (dev dashboard) |
| GET  | `/api/benchmark`   | Pass-through: benchmark summary (researcher page) |
| GET  | `/api/benchmark/log` | Pass-through of the 360-row x 8-KPI log; `?format=csv` streams the csv with its download header |
| GET  | `/api/ml-metrics`  | Pass-through: ML model metrics (researcher page) |
| POST | `/api/inspect`     | Engine inspect payload with each decomposition leg given bent `[lat,lng]` `points` for playback |
| GET  | `/healthz`         | Gateway + engine liveness |

`POST /api/map/route` body: `{ "origin": "cubao", "destination": "pasay", "profile": "safest" }`.
The response `geojson` is a `FeatureCollection` of one `LineString` per leg
(with a `color` per transit mode) plus `Point` features for origin / stops /
destination, and a `bounds` box for `map.fitBounds`.
