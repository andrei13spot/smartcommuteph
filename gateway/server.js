// node web + map gateway (the node side of the node + python setup).
// it serves the frontend, exposes the map api under /api/map/*, and turns the
// python engine's route output into geojson the leaflet frontend can draw.
// the python engine (routing + ml) runs separately on PYTHON_API_URL.
import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_DIR = path.resolve(__dirname, ".."); // repo root holds the .html/.css/.js
const PORT = process.env.PORT || 8080;
const PYTHON_API_URL = process.env.PYTHON_API_URL || "http://127.0.0.1:8000";

// line colors for the map polylines, keyed by mode
const MODE_COLORS = {
  "LRT-1": "#2e7d32",
  "LRT-2": "#6a1b9a",
  "MRT-3": "#1565c0",
  "EDSA-Bus": "#ef6c00",
  "Jeepney": "#c62828",
};

const app = express();
app.use(express.json());

// ---- helpers ----
async function callPython(pathname, { method = "GET", body } = {}) {
  const res = await fetch(`${PYTHON_API_URL}${pathname}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

// anchor id -> {lat, lng, name}, loaded lazily from the engine
let anchorIndex = null;
async function getAnchorIndex() {
  if (anchorIndex) return anchorIndex;
  const { ok, data } = await callPython("/api/anchors");
  if (!ok) throw new Error("could not load anchors from engine");
  anchorIndex = new Map(data.map((a) => [a.id, a]));
  return anchorIndex;
}

// color a node by its transit mode. for a route stop we know the arriving mode,
// for a station we pick the highest-priority line it serves (rail before street).
const MODE_PRIORITY = ["MRT-3", "LRT-2", "LRT-1", "EDSA-Bus", "Jeepney"];
function nodeColor(mode, lines) {
  if (mode && MODE_COLORS[mode]) return MODE_COLORS[mode];
  if (lines && lines.length) {
    for (const m of MODE_PRIORITY) if (lines.includes(m)) return MODE_COLORS[m];
  }
  return "#3b82f6";
}

function pointFeature(anchor, role, mode) {
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: [anchor.lng, anchor.lat] },
    properties: {
      id: anchor.id, name: anchor.name, role, mode: mode || null,
      lines: anchor.lines || null, color: nodeColor(mode, anchor.lines),
    },
  };
}

function lineFeature(a, b, mode) {
  return {
    type: "Feature",
    geometry: {
      type: "LineString",
      coordinates: [
        [a.lng, a.lat],
        [b.lng, b.lat],
      ],
    },
    properties: { mode, color: MODE_COLORS[mode] || "#334155" },
  };
}

// turn a python route response into geojson + bounds
async function routeToGeoJSON(route) {
  const anchors = await getAnchorIndex();
  const features = [];
  const segs = route.segments || [];

  if (segs.length === 0) {
    // origin == destination or no path: just drop the two endpoints
    for (const role of ["origin", "destination"]) {
      const a = anchors.get(route[role]?.id);
      if (a) features.push(pointFeature(a, role));
    }
  } else {
    // node list in order: first leg's origin, then every leg's target
    const nodeIds = [segs[0].from_id, ...segs.map((s) => s.to_id)];
    nodeIds.forEach((id, i) => {
      const a = anchors.get(id);
      if (!a) return;
      const role = i === 0 ? "origin" : i === nodeIds.length - 1 ? "destination" : "stop";
      const arrivingMode = i > 0 ? segs[i - 1].mode : null;
      features.push(pointFeature(a, role, arrivingMode));
    });
    for (const s of segs) {
      const a = anchors.get(s.from_id);
      const b = anchors.get(s.to_id);
      if (a && b) features.push(lineFeature(a, b, s.mode));
    }
  }

  const coords = features.flatMap((f) =>
    f.geometry.type === "Point"
      ? [f.geometry.coordinates]
      : f.geometry.coordinates
  );
  const bounds = boundsOf(coords);
  return { type: "FeatureCollection", features, bounds };
}

function boundsOf(coords) {
  if (coords.length === 0) return null;
  let minLat = Infinity, minLng = Infinity, maxLat = -Infinity, maxLng = -Infinity;
  for (const [lng, lat] of coords) {
    minLat = Math.min(minLat, lat); maxLat = Math.max(maxLat, lat);
    minLng = Math.min(minLng, lng); maxLng = Math.max(maxLng, lng);
  }
  return [[minLat, minLng], [maxLat, maxLng]];
}

// ---- contract endpoints (the agreed api contract) ----
// validate first before calling the engine
function checkOd(req, res, needProfile) {
  const { origin, destination, profile } = req.body || {};
  if (!origin || !destination || (needProfile && !profile)) {
    res.status(400).json({ error: "origin, destination" + (needProfile ? " and profile" : "") + " are required" });
    return false;
  }
  if (origin === destination) {
    res.status(400).json({ error: "origin and destination cannot be the same" });
    return false;
  }
  return true;
}

// geometry = list of [lat,lng] from origin to destination
async function routeGeometry(route) {
  const anchors = await getAnchorIndex();
  const segs = route.segments || [];
  if (!segs.length) return [];
  const ids = [segs[0].from_id, ...segs.map((s) => s.to_id)];
  return ids.map((id) => anchors.get(id)).filter(Boolean).map((a) => [a.lat, a.lng]);
}

// 8 kpis mapped from the engine response
function toKpis(route) {
  const s = route.summary;
  return {
    travel_time_min: s.time_min,
    distance_km: s.distance_km,
    fare_php: s.fare_discounted_php ?? s.fare_php,
    transfers: s.transfers,
    flood_risk_score: route.criteria.R.value,
    ridership_density_score: route.criteria.T.value,
    nodes_expanded: route.expanded_nodes,
    exec_ms: route.exec_ms,
  };
}

async function toContractResult(route) {
  return {
    profile: route.profile.id,
    origin: route.origin.id,
    destination: route.destination.id,
    geometry: await routeGeometry(route),
    kpis: toKpis(route),
    why_this_route: route.why,
    criteria: {
      T: route.criteria.T.value, F: route.criteria.F.value,
      R: route.criteria.R.value, P: route.criteria.P.value,
    },
  };
}

// isang route + kpis
app.post("/route", async (req, res) => {
  if (!checkOd(req, res, true)) return;
  try {
    const { ok, status, data } = await callPython("/api/route", { method: "POST", body: req.body });
    if (!ok) return res.status(status).json(data);
    res.json(await toContractResult(data));
  } catch (err) {
    res.status(502).json({ error: "engine unreachable", detail: String(err) });
  }
});

// 4 profiles + baseline = 5 results
app.post("/compare", async (req, res) => {
  if (!checkOd(req, res, false)) return;
  try {
    const { ok, status, data } = await callPython("/api/compare", { method: "POST", body: req.body });
    if (!ok) return res.status(status).json(data);
    const results = [];
    for (const r of data.routes) results.push(await toContractResult(r));
    res.json({ origin: data.origin.id, destination: data.destination.id, results });
  } catch (err) {
    res.status(502).json({ error: "engine unreachable", detail: String(err) });
  }
});

// ---- map api ----
app.get("/api/map/network", async (_req, res) => {
  try {
    const { ok, status, data } = await callPython("/api/network");
    if (!ok) return res.status(status).json(data);
    const byId = new Map(data.nodes.map((n) => [n.id, n]));
    const features = [];
    for (const n of data.nodes) features.push(pointFeature(n, "station"));
    for (const e of data.edges) {
      const a = byId.get(e.from_id);
      const b = byId.get(e.to_id);
      if (a && b) features.push(lineFeature(a, b, e.mode));
    }
    res.json({
      type: "FeatureCollection",
      features,
      bounds: boundsOf(features.flatMap((f) =>
        f.geometry.type === "Point" ? [f.geometry.coordinates] : f.geometry.coordinates)),
      colors: MODE_COLORS,
    });
  } catch (err) {
    res.status(502).json({ error: "engine unreachable", detail: String(err) });
  }
});

app.post("/api/map/route", async (req, res) => {
  try {
    const { ok, status, data } = await callPython("/api/route", { method: "POST", body: req.body });
    if (!ok) return res.status(status).json(data);
    const geojson = await routeToGeoJSON(data);
    res.json({ route: data, geojson, colors: MODE_COLORS });
  } catch (err) {
    res.status(502).json({ error: "engine unreachable", detail: String(err) });
  }
});

app.post("/api/map/compare", async (req, res) => {
  try {
    const { ok, status, data } = await callPython("/api/compare", { method: "POST", body: req.body });
    if (!ok) return res.status(status).json(data);
    const routes = [];
    for (const route of data.routes) {
      routes.push({ route, geojson: await routeToGeoJSON(route) });
    }
    res.json({ origin: data.origin, destination: data.destination, routes, colors: MODE_COLORS });
  } catch (err) {
    res.status(502).json({ error: "engine unreachable", detail: String(err) });
  }
});

// thin pass-throughs so the frontend stays same-origin
app.get("/api/map/anchors", async (_req, res) => {
  const { status, data } = await callPython("/api/anchors");
  res.status(status).json(data);
});
app.get("/api/map/profiles", async (_req, res) => {
  const { status, data } = await callPython("/api/profiles");
  res.status(status).json(data);
});

// dev dashboard status feed
app.get("/api/status", async (_req, res) => {
  try {
    const { status, data } = await callPython("/api/status");
    res.status(status).json(data);
  } catch (err) {
    res.status(502).json({ status: "down", error: "engine unreachable", detail: String(err) });
  }
});

// researcher dashboard feeds
app.get("/api/benchmark", async (req, res) => {
  const qs = new URLSearchParams(req.query).toString();
  const { status, data } = await callPython("/api/benchmark" + (qs ? "?" + qs : ""));
  res.status(status).json(data);
});
// 360 row benchmark log, csv or json (fetched raw since it can be csv text)
app.get("/api/benchmark/log", async (req, res) => {
  const qs = new URLSearchParams(req.query).toString();
  try {
    const r = await fetch(`${PYTHON_API_URL}/api/benchmark/log` + (qs ? "?" + qs : ""));
    const text = await r.text();
    res.status(r.status);
    res.set("Content-Type", r.headers.get("content-type") || "application/json");
    const cd = r.headers.get("content-disposition");
    if (cd) res.set("Content-Disposition", cd);
    res.send(text);
  } catch (err) {
    res.status(502).json({ error: "engine unreachable", detail: String(err) });
  }
});
app.get("/api/ml-metrics", async (_req, res) => {
  const { status, data } = await callPython("/api/ml-metrics");
  res.status(status).json(data);
});
app.post("/api/inspect", async (req, res) => {
  const { status, data } = await callPython("/api/inspect", { method: "POST", body: req.body });
  res.status(status).json(data);
});

app.get("/healthz", async (_req, res) => {
  const engine = await callPython("/api/health").catch(() => ({ ok: false }));
  res.json({ gateway: "ok", engine: engine.ok ? "ok" : "unreachable", python_api: PYTHON_API_URL });
});

// ---- static frontend ----
app.use(express.static(FRONTEND_DIR, { extensions: ["html"] }));

app.listen(PORT, () => {
  console.log(`smartcommute ph gateway on http://127.0.0.1:${PORT}`);
  console.log(`proxying routing engine at ${PYTHON_API_URL}`);
});
