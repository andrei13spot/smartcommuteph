// leaflet maps, one script for every page.
//   index.html    #network-map  -> the whole transit network
//   location.html #location-map -> origin/destination preview
//   result.html   #result-map   -> the computed route for the saved trip
// data comes from the node gateway's map api (/api/map/*).
// markers are circlemarkers so there are no image files to 404.
(function () {
  const TILES = {
    dark: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    light: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
  };
  const ATTRIB = '&copy; OpenStreetMap &copy; CARTO';
  const METRO_CENTER = [14.59, 121.0];
  const ROLE_STYLE = {
    origin: { color: "#10b981", fill: "#10b981", r: 8 },
    destination: { color: "#ef4444", fill: "#ef4444", r: 8 },
    stop: { color: "#ffffff", fill: "#64748b", r: 5 },
    station: { color: "#ffffff", fill: "#3b82f6", r: 5 },
  };

  function baseMap(elId, theme) {
    const map = L.map(elId, { zoomControl: true, scrollWheelZoom: false }).setView(METRO_CENTER, 12);
    L.tileLayer(TILES[theme], { attribution: ATTRIB, maxZoom: 19 }).addTo(map);
    return map;
  }

  function styleLine(feature) {
    return { color: feature.properties.color || "#334155", weight: 5, opacity: 0.9 };
  }

  function pointToLayer(feature, latlng) {
    const s = ROLE_STYLE[feature.properties.role] || ROLE_STYLE.stop;
    const marker = L.circleMarker(latlng, {
      radius: s.r, color: s.color, weight: 2, fillColor: s.fill, fillOpacity: 1,
    });
    if (feature.properties.name) {
      const mode = feature.properties.mode ? ` · ${feature.properties.mode}` : "";
      marker.bindTooltip(`${feature.properties.name}${mode}`, { direction: "top" });
    }
    return marker;
  }

  function drawCollection(map, geojson) {
    const layer = L.geoJSON(geojson, { style: styleLine, pointToLayer }).addTo(map);
    if (geojson.bounds) {
      map.fitBounds(geojson.bounds, { padding: [40, 40], maxZoom: 14 });
    } else {
      map.fitBounds(layer.getBounds(), { padding: [40, 40], maxZoom: 14 });
    }
    return layer;
  }

  async function getJSON(url, opts) {
    const res = await fetch(url, opts);
    if (!res.ok) throw new Error(`${url} -> ${res.status}`);
    return res.json();
  }

  // index.html: the whole network
  async function initNetworkMap() {
    const map = baseMap("network-map", "dark");
    try {
      const geojson = await getJSON("/api/map/network");
      drawCollection(map, geojson);
    } catch (err) {
      console.warn("network map unavailable:", err);
    }
  }

  // location.html: origin/destination preview
  async function initLocationMap() {
    const map = baseMap("location-map", "light");
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
      const oId = selects[0]?.value || "cubao";
      const dId = selects[1]?.value || "pasay";
      const o = byId.get(oId);
      const d = byId.get(dId);
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
    const map = baseMap("result-map", "dark");
    const origin = localStorage.getItem("smartCommute_routeOriginId") || "cubao";
    const destination = localStorage.getItem("smartCommute_routeDestId") || "pasay";
    const profile = localStorage.getItem("smartCommute_selectedProfile") || "safest";
    try {
      const { geojson } = await getJSON("/api/map/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ origin, destination, profile }),
      });
      drawCollection(map, geojson);
    } catch (err) {
      console.warn("route map unavailable:", err);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (typeof L === "undefined") return; // leaflet not on this page
    if (document.getElementById("network-map")) initNetworkMap();
    if (document.getElementById("location-map")) initLocationMap();
    if (document.getElementById("result-map")) initResultMap();
  });
})();
