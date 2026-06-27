// leaflet maps, one script for every page.
//   index.html    #network-map  -> the whole transit network
//   location.html #location-map -> origin/destination preview
//   result.html   #result-map   -> the computed route for the saved trip
//   compare.html  .compare-card-map -> a mini route map per profile
// data comes from the node gateway's map api (/api/map/*).
// nodes are colored by transit mode and use a glowing divicon dot.
(function () {
  const TILES = {
    dark: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    light: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
  };
  const ATTRIB = '&copy; OpenStreetMap &copy; CARTO';
  const METRO_CENTER = [14.59, 121.0];
  // origin/destination keep fixed colors, everything else is colored by mode
  const ROLE_COLOR = { origin: "#10b981", destination: "#ef4444" };

  // glowing dot marker, colored by the node's mode color
  function nodeIcon(color, big) {
    const size = big ? 18 : 13;
    return L.divIcon({
      className: "map-node",
      html: `<span class="map-node-dot${big ? " big" : ""}" style="--node:${color}"></span>`,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    });
  }

  function pointToLayer(feature, latlng) {
    const p = feature.properties;
    const big = p.role === "origin" || p.role === "destination";
    const color = ROLE_COLOR[p.role] || p.color || "#3b82f6";
    const marker = L.marker(latlng, { icon: nodeIcon(color, big), keyboard: false });
    if (p.name) {
      const mode = p.mode ? ` · ${p.mode}` : "";
      marker.bindTooltip(`${p.name}${mode}`, { direction: "top" });
    }
    return marker;
  }

  function styleLine(feature) {
    return { color: feature.properties.color || "#334155", weight: 5, opacity: 0.95 };
  }

  // keep the map sized to its container: recompute after paint and on resize.
  // this is what makes the maps responsive when the layout/viewport changes.
  function keepSized(map, el, onResize) {
    requestAnimationFrame(() => {
      map.invalidateSize();
      requestAnimationFrame(() => map.invalidateSize());
    });
    if (window.ResizeObserver) {
      const ro = new ResizeObserver(() => {
        map.invalidateSize();
        if (onResize) onResize();
      });
      ro.observe(el);
    }
  }

  function baseMap(elId, theme, opts) {
    const el = typeof elId === "string" ? document.getElementById(elId) : elId;
    const map = L.map(el, Object.assign({ zoomControl: true, scrollWheelZoom: false }, opts || {}))
      .setView(METRO_CENTER, 12);
    L.tileLayer(TILES[theme], { attribution: ATTRIB, maxZoom: 19 }).addTo(map);
    return { map, el };
  }

  function drawCollection(map, geojson) {
    const layer = L.geoJSON(geojson, { style: styleLine, pointToLayer }).addTo(map);
    const b = geojson.bounds || layer.getBounds();
    if (b) map.fitBounds(b, { padding: [30, 30], maxZoom: 14 });
    return layer;
  }

  async function getJSON(url, opts) {
    const res = await fetch(url, opts);
    if (!res.ok) throw new Error(`${url} -> ${res.status}`);
    return res.json();
  }

  // small legend showing which transit modes the route uses
  function buildModeLegend(containerId, modes, colors) {
    const el = document.getElementById(containerId);
    if (!el || !modes || !modes.length) return;
    el.innerHTML =
      `<span class="route-legend-title">Modes used</span>` +
      modes
        .map((m) => {
          const c = (colors && colors[m]) || "#334155";
          return `<span class="route-legend-item"><span class="route-legend-dot" style="background:${c}"></span>${m}</span>`;
        })
        .join("");
  }

  // index.html: the whole network
  async function initNetworkMap() {
    const { map, el } = baseMap("network-map", "dark", { minZoom: 10 });
    let bounds = null;
    keepSized(map, el, () => { if (bounds) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 14 }); });
    try {
      const geojson = await getJSON("/api/map/network");
      drawCollection(map, geojson);
      bounds = geojson.bounds;
    } catch (err) {
      console.warn("network map unavailable:", err);
    }
  }

  // location.html: origin/destination preview
  async function initLocationMap() {
    const { map, el } = baseMap("location-map", "dark");
    keepSized(map, el);
    let anchors = [];
    try {
      anchors = await getJSON("/api/map/anchors");
    } catch (err) {
      console.warn("anchors unavailable:", err);
      return;
    }
    const byId = new Map(anchors.map((a) => [a.id, a]));
    let layer = null;
    const selects = document.querySelectorAll(".location-panel select");

    function render() {
      const o = byId.get(selects[0]?.value || "cubao");
      const d = byId.get(selects[1]?.value || "pasay");
      if (!o || !d) return;
      const gj = {
        type: "FeatureCollection",
        features: [
          { type: "Feature", geometry: { type: "Point", coordinates: [o.lng, o.lat] }, properties: { role: "origin", name: o.name } },
          { type: "Feature", geometry: { type: "Point", coordinates: [d.lng, d.lat] }, properties: { role: "destination", name: d.name } },
          { type: "Feature", geometry: { type: "LineString", coordinates: [[o.lng, o.lat], [d.lng, d.lat]] }, properties: { color: "#3b82f6" } },
        ],
      };
      if (layer) map.removeLayer(layer);
      layer = L.geoJSON(gj, { style: styleLine, pointToLayer }).addTo(map);
      map.fitBounds(layer.getBounds(), { padding: [50, 50], maxZoom: 13 });
    }

    selects.forEach((s) => s.addEventListener("change", render));
    render();
  }

  // result.html: the computed route
  async function initResultMap() {
    const { map, el } = baseMap("result-map", "dark");
    keepSized(map, el);
    const origin = localStorage.getItem("smartCommute_routeOriginId") || "cubao";
    const destination = localStorage.getItem("smartCommute_routeDestId") || "pasay";
    const profile = localStorage.getItem("smartCommute_selectedProfile") || "safest";
    try {
      const { geojson, route, colors } = await getJSON("/api/map/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ origin, destination, profile }),
      });
      drawCollection(map, geojson);
      buildModeLegend("result-legend", route.summary.modes, colors);
    } catch (err) {
      console.warn("route map unavailable:", err);
    }
  }

  // fill a compare card's numbers from the real route so they match the map
  function fillCompareCard(card, route) {
    const set = (sel, val) => { const e = card.querySelector(sel); if (e) e.innerText = val; };
    const s = route.summary;
    set(".compare-card-title", route.prioritized.title);
    set(".compare-card-body p.text-secondary", route.prioritized.subtitle);
    const metrics = [
      ["TIME", `${Math.round(s.time_min)}m`],
      ["FARE", `₱${Math.round(s.fare_php)}`],
      ["TRANSFERS", String(s.transfers)],
      ["FLOOD", route.criteria.R.level],
    ];
    card.querySelectorAll(".compare-metric").forEach((el, i) => {
      if (!metrics[i]) return;
      const lbl = el.querySelector(".compare-metric-label");
      const val = el.querySelector(".compare-metric-value");
      if (lbl) lbl.innerText = metrics[i][0];
      if (val) val.innerText = metrics[i][1];
    });
    set(".compare-card-route", `${route.origin.name} → ${s.modes.join(" → ")} → ${route.destination.name}`);
  }

  // compare.html: a small static route map inside each profile card
  async function initCompareMaps() {
    const origin = localStorage.getItem("smartCommute_routeOriginId") || "cubao";
    const destination = localStorage.getItem("smartCommute_routeDestId") || "pasay";
    let data;
    try {
      data = await getJSON("/api/map/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ origin, destination }),
      });
    } catch (err) {
      console.warn("compare maps unavailable:", err);
      return;
    }
    for (const item of data.routes) {
      const id = item.route.profile.id;
      const card = document.querySelector(`.compare-card[data-profile="${id}"]`);
      const el = card && card.querySelector(".compare-card-map");
      if (!el) continue;
      fillCompareCard(card, item.route);
      el.classList.add("has-map");
      const mini = L.map(el, {
        zoomControl: false, attributionControl: false, dragging: false,
        scrollWheelZoom: false, doubleClickZoom: false, boxZoom: false,
        keyboard: false, tap: false,
      }).setView(METRO_CENTER, 11);
      L.tileLayer(TILES.dark, { maxZoom: 19 }).addTo(mini);
      const layer = L.geoJSON(item.geojson, { style: styleLine, pointToLayer }).addTo(mini);
      const b = item.geojson.bounds || layer.getBounds();
      keepSized(mini, el, () => { if (b) mini.fitBounds(b, { padding: [16, 16], maxZoom: 13 }); });
      if (b) mini.fitBounds(b, { padding: [16, 16], maxZoom: 13 });
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (typeof L === "undefined") return; // leaflet not on this page
    if (document.getElementById("network-map")) initNetworkMap();
    if (document.getElementById("location-map")) initLocationMap();
    if (document.getElementById("result-map")) initResultMap();
    if (document.querySelector(".compare-card-map")) initCompareMaps();
  });
})();
