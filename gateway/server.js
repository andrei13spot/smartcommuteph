// node web + map gateway (the node side of the node + python setup).
// it serves the frontend, exposes the map api under /api/map/*, and turns the
// python engine's route output into geojson the leaflet frontend can draw.
// the python engine (routing + ml) runs separately on PYTHON_API_URL.
import express from "express";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_DIR = path.resolve(__dirname, ".."); // repo root holds the .html/.css/.js
const PORT = process.env.PORT || 8080;
const PYTHON_API_URL = process.env.PYTHON_API_URL || "http://127.0.0.1:8000";

// real track polylines (dotc gtfs 2013 shapes.txt) so rail/busway segments are
// drawn along the actual alignment instead of straight station-to-station
// chords. drawing-only: distances and fares stay on the calibrated values.
const SHAPES_PATH = path.resolve(__dirname, "../backend/app/data/line_shapes.json");
let LINE_SHAPES = { lines: {}, aliases: {} };
try {
  LINE_SHAPES = JSON.parse(fs.readFileSync(SHAPES_PATH, "utf-8"));
} catch {
  console.warn("line_shapes.json not found - segments draw straight");
}

const SNAP_KM = 0.8; // an endpoint further than this off its line's shape falls back to straight

function shapeFor(mode) {
  const lines = LINE_SHAPES.lines || {};
  const key = lines[mode] ? mode : (LINE_SHAPES.aliases || {})[mode];
  return key && lines[key] ? lines[key].points : null;
}

// closest point ON the polyline (not just the nearest vertex - snapping to a
// vertex that sits behind the station made the line double back and draw a
// little spur at each stop). planar approx is fine at metro scale.
function projectOnShape(pts, lat, lng) {
  const ky = 110.574, kx = 111.32 * Math.cos((lat * Math.PI) / 180);
  let best = null;
  for (let i = 0; i < pts.length - 1; i++) {
    const ax = (pts[i][1] - lng) * kx, ay = (pts[i][0] - lat) * ky;
    const bx = (pts[i + 1][1] - lng) * kx, by = (pts[i + 1][0] - lat) * ky;
    const dx = bx - ax, dy = by - ay;
    const len2 = dx * dx + dy * dy;
    let t = len2 ? -(ax * dx + ay * dy) / len2 : 0;
    t = Math.max(0, Math.min(1, t));
    const px = ax + t * dx, py = ay + t * dy;
    const d = Math.sqrt(px * px + py * py);
    if (!best || d < best.d) best = { d, seg: i, t,
      lat: pts[i][0] + t * (pts[i + 1][0] - pts[i][0]),
      lng: pts[i][1] + t * (pts[i + 1][1] - pts[i][1]) };
  }
  return best;
}

// [lat,lng] waypoints from a to b along the line's shape (endpoints included),
// or null when the shape does not cover this hop (then the caller draws
// straight). the path runs monotonically between the two projections, so it
// never backtracks past a station.
function bendPoints(a, b, mode) {
  const pts = shapeFor(mode);
  if (!pts) return null;
  const pa = projectOnShape(pts, a.lat, a.lng);
  const pb = projectOnShape(pts, b.lat, b.lng);
  if (!pa || !pb || pa.d > SNAP_KM || pb.d > SNAP_KM) return null;
  const ka = pa.seg + pa.t, kb = pb.seg + pb.t;
  if (Math.abs(ka - kb) < 1e-9) return null;
  const fwd = ka < kb;
  const [p1, p2] = fwd ? [pa, pb] : [pb, pa];
  const path = [[p1.lat, p1.lng], ...pts.slice(p1.seg + 1, p2.seg + 1), [p2.lat, p2.lng]];
  if (!fwd) path.reverse();
  return [[a.lat, a.lng], ...path, [b.lat, b.lng]];
}

const MODE_COLORS = {
  "LRT-1": "#ef4444",
  "LRT-2": "#a855f7",
  "MRT-3": "#3b82f6",
  "EDSA-Bus": "#10b981",
  "Jeepney": "#f59e0b",
};

process.on("unhandledRejection", (err) => {
  console.error("unhandled rejection (kept alive):", err && err.message ? err.message : err);
});

const app = express();
// the import endpoint receives a whole benchmark log csv as text
app.use(express.json({ limit: "3mb" }));

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

// node id -> {lat, lng, name}, loaded lazily from the engine. uses /api/network
// (all nodes incl. the 300m virtual jeepney stops) so route geometry through a
// jeepney chain resolves; /api/anchors only has the 10 od anchors.
let anchorIndex = null;
async function getAnchorIndex() {
  if (anchorIndex) return anchorIndex;
  const { ok, data } = await callPython("/api/network");
  if (!ok) throw new Error("could not load network nodes from engine");
  anchorIndex = new Map(data.nodes.map((a) => [a.id, a]));
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

// bent waypoints for every leg of a route, in travel order (null = no shape,
// draw straight). when the ride continues on the same line through a node,
// that node's own coordinate is dropped between the two legs: an anchor can
// sit a few hundred metres off the track (cubao is the lrt-2 station), and
// keeping it made the line leave the track and come back at a stop the rider
// never gets off at. real transfers and the two route ends keep the node.
function bendRoute(segs, anchors) {
  const legs = segs.map((s) => {
    const a = anchors.get(s.from_id);
    const b = anchors.get(s.to_id);
    return a && b ? bendPoints(a, b, s.mode) : null;
  });
  for (let i = 0; i + 1 < legs.length; i++) {
    if (legs[i] && legs[i + 1] && segs[i].mode === segs[i + 1].mode && segs[i].to_id === segs[i + 1].from_id) {
      legs[i] = legs[i].slice(0, -1);
      legs[i + 1] = legs[i + 1].slice(1);
    }
  }
  return legs;
}

// pts (optional) are already-bent [lat,lng] waypoints for this leg
function lineFeature(a, b, mode, pts) {
  const bent = pts || bendPoints(a, b, mode);
  const coordinates = bent
    ? bent.map(([lat, lng]) => [lng, lat])
    : [[a.lng, a.lat], [b.lng, b.lat]];
  return {
    type: "Feature",
    geometry: { type: "LineString", coordinates },
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
    const bent = bendRoute(segs, anchors);
    segs.forEach((s, i) => {
      const a = anchors.get(s.from_id);
      const b = anchors.get(s.to_id);
      if (a && b) features.push(lineFeature(a, b, s.mode, bent[i]));
    });
  }

  return { type: "FeatureCollection", features, bounds: featureBounds(features) };
}

function featureBounds(features) {
  const coords = features.flatMap((f) =>
    f.geometry.type === "Point" ? [f.geometry.coordinates] : f.geometry.coordinates);
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

// geometry = [lat,lng] from origin to destination: the route's leg LineStrings
// (already bent along the track by routeToGeoJSON) joined end to end
async function routeGeometry(route) {
  const { features } = await routeToGeoJSON(route);
  const out = [];
  for (const f of features) {
    if (f.geometry.type !== "LineString") continue;
    const pts = f.geometry.coordinates.map(([lng, lat]) => [lat, lng]);
    const last = out[out.length - 1];
    const same = last && last[0] === pts[0][0] && last[1] === pts[0][1];
    out.push(...(same ? pts.slice(1) : pts));
  }
  return out;
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

// every proxying handler answers 502 instead of crashing the process when the engine is down.
// downBody = extra fields put in front of the 502 json (the status feed adds status: "down")
const guard = (fn, downBody = {}) => async (req, res) => {
  try { await fn(req, res); }
  catch (err) { res.status(502).json({ ...downBody, error: "engine unreachable", detail: String(err) }); }
};

// isang route + kpis
app.post("/route", guard(async (req, res) => {
  if (!checkOd(req, res, true)) return;
  const { ok, status, data } = await callPython("/api/route", { method: "POST", body: req.body });
  if (!ok) return res.status(status).json(data);
  res.json(await toContractResult(data));
}));

// 4 profiles + baseline = 5 results
app.post("/compare", guard(async (req, res) => {
  if (!checkOd(req, res, false)) return;
  const { ok, status, data } = await callPython("/api/compare", { method: "POST", body: req.body });
  if (!ok) return res.status(status).json(data);
  const results = [];
  for (const r of data.routes) results.push(await toContractResult(r));
  res.json({ origin: data.origin.id, destination: data.destination.id, results });
}));

// ---- map api ----
app.get("/api/map/network", guard(async (_req, res) => {
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
    bounds: featureBounds(features),
    colors: MODE_COLORS,
  });
}));

app.post("/api/map/route", guard(async (req, res) => {
  const { ok, status, data } = await callPython("/api/route", { method: "POST", body: req.body });
  if (!ok) return res.status(status).json(data);
  const geojson = await routeToGeoJSON(data);
  res.json({ route: data, geojson, colors: MODE_COLORS });
}));

app.post("/api/map/compare", guard(async (req, res) => {
  const { ok, status, data } = await callPython("/api/compare", { method: "POST", body: req.body });
  if (!ok) return res.status(status).json(data);
  const routes = [];
  for (const route of data.routes) {
    routes.push({ route, geojson: await routeToGeoJSON(route) });
  }
  res.json({ origin: data.origin, destination: data.destination, routes, colors: MODE_COLORS });
}));

// thin pass-throughs so the frontend stays same-origin. each one is wrapped:
// if the engine is down these must answer 502, not crash the gateway process
// (an unhandled fetch rejection exits node)
function passthrough(enginePath, downBody = {}) {
  return guard(async (req, res) => {
    const qs = new URLSearchParams(req.query).toString();
    const { status, data } = await callPython(enginePath + (qs ? "?" + qs : ""));
    res.status(status).json(data);
  }, downBody);
}
app.get("/api/map/anchors", passthrough("/api/anchors"));
app.get("/api/map/profiles", passthrough("/api/profiles"));

// the jeepney routes as drawn lines, straight from the virtual stops geojson
// (read-only). every route uses the one jeepney colour, like the rest of the
// app; the file's own per-route stroke colours are ignored on purpose.
// the network maps draw these instead of the 2,700 stop dots.
const ROUTES_PATH = path.resolve(__dirname, "../backend/app/data/virtual_stops.geojson");
let routeLines = null;
app.get("/api/map/routes", (_req, res) => {
  try {
    if (!routeLines) {
      const gj = JSON.parse(fs.readFileSync(ROUTES_PATH, "utf-8"));
      routeLines = {
        type: "FeatureCollection",
        features: gj.features
          .filter((f) => f.geometry && f.geometry.type === "LineString")
          .map((f) => ({
            type: "Feature",
            geometry: f.geometry,
            properties: {
              route: f.properties.route || f.properties.name || null,
              category: f.properties.category || null,
              mode: "Jeepney",
              color: MODE_COLORS.Jeepney,
            },
          })),
      };
    }
    res.json(routeLines);
  } catch (err) {
    res.status(500).json({ error: "route lines unavailable", detail: String(err) });
  }
});

// dev dashboard status feed
app.get("/api/status", passthrough("/api/status", { status: "down" }));

// researcher dashboard feeds
app.get("/api/benchmark", passthrough("/api/benchmark"));
// 360 row benchmark log, csv or json (fetched raw since it can be csv text)
app.get("/api/benchmark/log", guard(async (req, res) => {
  const qs = new URLSearchParams(req.query).toString();
  const r = await fetch(`${PYTHON_API_URL}/api/benchmark/log` + (qs ? "?" + qs : ""));
  const text = await r.text();
  res.status(r.status);
  res.set("Content-Type", r.headers.get("content-type") || "application/json");
  const cd = r.headers.get("content-disposition");
  if (cd) res.set("Content-Disposition", cd);
  res.send(text);
}));
app.get("/api/ml-metrics", passthrough("/api/ml-metrics"));

// import and export: the pdf reports are passed through as files, the import
// summary as json
async function sendEngineFile(res, enginePath, init = {}) {
  const r = await fetch(`${PYTHON_API_URL}${enginePath}`, init);
  const buf = Buffer.from(await r.arrayBuffer());
  res.status(r.status);
  res.set("Content-Type", r.headers.get("content-type") || "application/octet-stream");
  const cd = r.headers.get("content-disposition");
  if (cd) res.set("Content-Disposition", cd);
  res.send(buf);
}
app.get("/api/benchmark/report", guard(async (req, res) => {
  const qs = new URLSearchParams(req.query).toString();
  await sendEngineFile(res, "/api/benchmark/report" + (qs ? "?" + qs : ""));
}));
app.post("/api/benchmark/import", guard(async (req, res) => {
  const { status, data } = await callPython("/api/benchmark/import", { method: "POST", body: req.body });
  res.status(status).json(data);
}));
app.post("/api/benchmark/import/report", guard(async (req, res) => {
  await sendEngineFile(res, "/api/benchmark/import/report", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req.body),
  });
}));
app.post("/api/inspect", guard(async (req, res) => {
  const { status, data } = await callPython("/api/inspect", { method: "POST", body: req.body });
  // give each route leg its bent [lat,lng] waypoints so the playback overlay
  // follows the real track like the route map does
  if (status === 200 && data && Array.isArray(data.decomposition)) {
    try {
      const anchors = await getAnchorIndex();
      const bent = bendRoute(data.decomposition, anchors);
      data.decomposition.forEach((leg, i) => {
        if (bent[i]) leg.points = bent[i];
      });
      if (Array.isArray(data.baseline_legs)) {
        const bentBase = bendRoute(data.baseline_legs, anchors);
        data.baseline_legs.forEach((leg, i) => {
          if (bentBase[i]) leg.points = bentBase[i];
        });
      }
    } catch {}
  }
  res.status(status).json(data);
}));

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
