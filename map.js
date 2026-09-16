// leaflet maps, one script for every page.
//   index.html    #network-map  -> the whole transit network
//   location.html #location-map -> origin/destination preview
//   result.html   #result-map   -> the computed route for the saved trip
//   compare.html  .compare-card-map -> a mini route map per profile
// data comes from the node gateway's map api (/api/map/*).
// nodes are colored by transit mode and use a glowing divicon dot.
(function () {
  // carto's free anonymous basemaps now stamp an "api key required" watermark
  // on keyless requests, so we use keyless providers instead: esri's dark
  // canvas (no key needed) and standard osm for light.
  // note esri's tile path is {z}/{y}/{x} - y before x.
  const TILES = {
    dark: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    light: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  };
  const ATTRIB = 'Esri, HERE, Garmin, &copy; OpenStreetMap contributors';
  // esri dark canvas only serves native tiles to zoom 16; leaflet upscales past that
  function tileOpts(theme, withAttrib) {
    const opts = { maxZoom: 19, maxNativeZoom: theme === "light" ? 19 : 16 };
    if (withAttrib) opts.attribution = ATTRIB;
    return opts;
  }
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
    L.tileLayer(TILES[theme], tileOpts(theme, true)).addTo(map);
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
      modes
        .map((m) => {
          const c = (colors && colors[m]) || "#334155";
          return `<div class="legend-item text-white"><span class="dot" style="background-color:${c}; color:${c};"></span> ${m}</div>`;
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
      if (layer) map.removeLayer(layer);
      
      const features = [];
      const oVal = selects[0]?.value;
      const dVal = selects[1]?.value;
      
      if (oVal) {
        const o = byId.get(oVal);
        if (o) features.push({ type: "Feature", geometry: { type: "Point", coordinates: [o.lng, o.lat] }, properties: { role: "origin", name: o.name } });
      }
      
      if (dVal) {
        const d = byId.get(dVal);
        if (d) features.push({ type: "Feature", geometry: { type: "Point", coordinates: [d.lng, d.lat] }, properties: { role: "destination", name: d.name } });
      }

      if (features.length === 0) return;

      const gj = { type: "FeatureCollection", features };
      layer = L.geoJSON(gj, { 
        style: styleLine, 
        pointToLayer: (feature, latlng) => {
          const marker = pointToLayer(feature, latlng);
          if (feature.properties.name) {
            marker.unbindTooltip();
            marker.bindTooltip(feature.properties.name, { permanent: true, direction: "top", className: "fw-bold bg-dark text-white border-secondary" });
          }
          return marker;
        }
      }).addTo(map);
      map.fitBounds(layer.getBounds(), { padding: [50, 50], maxZoom: 13 });
    }

    selects.forEach((s) => s.addEventListener("change", render));
    render();
  }

  // result.html: the a* expansion animation while the route loads, then the
  // computed route. the yellow wave is every node the search actually popped -
  // the visible half of the pruning story.
  async function playExpansion(map, el, origin, destination, profile) {
    // the search cloud runs on a CANVAS renderer: one bitmap layer instead of
    // thousands of svg nodes, so it stays smooth even at ~2,400 expansions.
    // when the route is ready the cloud fades out gradually - no hard cut.
    const label = document.createElement("div");
    label.className = "astar-loading";
    label.style.cssText = "position:absolute;top:12px;left:50%;transform:translateX(-50%);z-index:1000;" +
      "background:rgba(15,23,42,.85);color:#ffcc02;padding:6px 14px;border-radius:999px;" +
      "font-size:.78rem;font-weight:600;letter-spacing:.03em;pointer-events:none;";
    label.innerText = "Running A* · pruning the search space…";
    el.style.position = el.style.position || "relative";
    el.appendChild(label);
    try {
      const studentMode = localStorage.getItem("smartCommute_studentMode") === "true";
      const passenger_type = studentMode ? "student" : "regular";
      const [inspect, network] = await Promise.all([
        getJSON("/api/inspect", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ origin, destination, profile, passenger_type }) }),
        getJSON("/api/map/network"),
      ]);
      const pos = {};
      (network.features || []).forEach((f) => {
        if (f.geometry && f.geometry.type === "Point" && f.properties && f.properties.id)
          pos[f.properties.id] = f.geometry.coordinates;
      });
      const canvas = L.canvas({ padding: 0.3 });
      const order = inspect.expanded_order || [];
      const layers = [];
      const chunk = Math.max(1, Math.ceil(order.length / 60));
      for (let i = 0; i < order.length; i += chunk) {
        for (const id of order.slice(i, i + chunk)) {
          const c = pos[id];
          if (!c) continue;
          layers.push(L.circleMarker([c[1], c[0]], { renderer: canvas, radius: 4,
            color: "#ffcc02", fillColor: "#ff9500", fillOpacity: 0.45, weight: 1 }).addTo(map));
        }
        await new Promise((r) => setTimeout(r, 28));
      }
      label.innerText = `Pruned: ${inspect.expanded_nodes} nodes explored vs ${inspect.baseline_nodes} baseline`;
      // graceful fade: step the whole cloud's opacity down, then remove
      return () => {
        let op = 0.45;
        const fade = setInterval(() => {
          op -= 0.06;
          if (op <= 0) {
            clearInterval(fade);
            layers.forEach((m) => { try { map.removeLayer(m); } catch (e) {} });
            try { label.remove(); } catch (e) {}
            return;
          }
          layers.forEach((m) => { try { m.setStyle({ fillOpacity: op, opacity: op }); } catch (e) {} });
        }, 90);
      };
    } catch (err) {
      try { label.remove(); } catch (e) {}
      return () => {};
    }
  }

  async function initResultMap() {
    const { map, el } = baseMap("result-map", "dark");
    keepSized(map, el);
    const origin = localStorage.getItem("smartCommute_routeOriginId");
    const destination = localStorage.getItem("smartCommute_routeDestId");
    const profile = localStorage.getItem("smartCommute_selectedProfile");
    try {
      const animation = playExpansion(map, el, origin, destination, profile);
      const studentMode = localStorage.getItem("smartCommute_studentMode") === "true";
      const passenger_type = studentMode ? "student" : "regular";
      const { geojson, route, colors } = await getJSON("/api/map/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ origin, destination, profile, passenger_type }),
      });
      const fadeOut = await animation;
      window.currentResultMap = map;
      window.currentRouteGeoJSON = geojson;
      drawCollection(map, geojson);
      if (fadeOut) setTimeout(fadeOut, 900);
      buildModeLegend("result-legend", route.summary.modes, colors);
      fillResultTiles(route);

      // Update the route breakdown container if the function exists
      if (window.renderResultRouteBreakdown) {
          window.renderResultRouteBreakdown(route);
      }
    } catch (err) {
      console.warn("route map unavailable:", err);
    }
  }

  // result.html: overwrite the canned headline tiles with the engine's real
  // numbers once the route arrives (script.js paints profile placeholders at
  // load; this runs after the fetch so the live values always win)
  function fillResultTiles(route) {
    const s = route.summary;
    const set = (id, val) => { const e = document.getElementById(id); if (e) e.innerText = val; };
    const fare = s.fare_discounted_php != null ? s.fare_discounted_php : s.fare_php;
    const timeVal = Math.round(s.time_min) + "m";
    const fareVal = "₱" + Math.round(fare);
    const transfersVal = String(s.transfers);
    const floodVal = route.criteria.R.level;
    const crowdVal = route.criteria.T.level;

    const pr = route.profile.priority;
    let metrics = [];
    if (route.profile.id === "uncrowded") {
        metrics = [
            { l: "Time", v: timeVal }, { l: "Fare", v: fareVal }, { l: "Transfers", v: transfersVal }, { l: "Flood", v: floodVal }
        ];
    } else if (route.profile.id === "cheapest") {
        metrics = [
            { l: "Time", v: timeVal }, { l: "Crowd", v: crowdVal }, { l: "Transfers", v: transfersVal }, { l: "Flood", v: floodVal }
        ];
    } else if (route.profile.id === "safest") {
        metrics = [
            { l: "Time", v: timeVal }, { l: "Fare", v: fareVal }, { l: "Transfers", v: transfersVal }, { l: "Crowd", v: crowdVal }
        ];
    } else { // convenient
        metrics = [
            { l: "Time", v: timeVal }, { l: "Fare", v: fareVal }, { l: "Crowd", v: crowdVal }, { l: "Flood Risk", v: floodVal }
        ];
    }

    set("detail-1-label", metrics[0].l); set("detail-1-value", metrics[0].v);
    set("detail-2-label", metrics[1].l); set("detail-2-value", metrics[1].v);
    set("detail-3-label", metrics[2].l); set("detail-3-value", metrics[2].v);
    set("detail-4-label", metrics[3].l); set("detail-4-value", metrics[3].v);

    // headline = the profile's prioritized number, live
    const headline = pr === "F" ? "₱" + Math.round(fare)
      : pr === "T" ? crowdVal
      : pr === "R" ? floodVal
      : transfersVal;
    const sub = pr === "F" ? "Lowest total fare" : pr === "T" ? "Crowd Level"
      : pr === "R" ? "Flood risk" : "Vehicle Changes";
    set("dynamic-result-summary", headline);
    set("dynamic-result-sub", sub);
    // the why-this-route card, straight from the engine
    if (route.why) {
      set("why-heading", route.why.heading || route.why.title || "");
      set("why-description", route.why.description || route.why.text || "");
    }
  }

  // fill a compare card's numbers from the real route so they match the map
  function fillCompareCard(card, route) {
    const set = (sel, val) => { const e = card.querySelector(sel); if (e) e.innerText = val; };
    const s = route.summary;
    const timeVal = `${Math.round(s.time_min)}m`;
    const fareVal = `₱${Math.round(s.fare_discounted_php != null ? s.fare_discounted_php : s.fare_php)}`;
    const transfersVal = String(s.transfers);
    const floodVal = route.criteria.R.level;
    const crowdVal = route.criteria.T.level;
    
    let metrics = [];
    if (route.profile.id === "uncrowded") {
        metrics = [ ["TIME", timeVal], ["FARE", fareVal], ["TRANSFERS", transfersVal], ["FLOOD", floodVal] ];
    } else if (route.profile.id === "cheapest") {
        metrics = [ ["TIME", timeVal], ["CROWD", crowdVal], ["TRANSFERS", transfersVal], ["FLOOD", floodVal] ];
    } else if (route.profile.id === "safest") {
        metrics = [ ["TIME", timeVal], ["FARE", fareVal], ["TRANSFERS", transfersVal], ["CROWD", crowdVal] ];
    } else {
        metrics = [ ["TIME", timeVal], ["FARE", fareVal], ["CROWD", crowdVal], ["FLOOD RISK", floodVal] ];
    }

    card.dataset.routeData = JSON.stringify(route);
    set(".compare-card-title", route.prioritized.title);
    set(".compare-card-body p.text-secondary", route.prioritized.subtitle);
    
    card.querySelectorAll(".compare-metric").forEach((el, i) => {
      if (!metrics[i]) return;
      const lbl = el.querySelector(".compare-metric-label");
      const val = el.querySelector(".compare-metric-value");
      if (lbl) lbl.innerText = metrics[i][0];
      if (val) val.innerText = metrics[i][1];
    });
    set(".compare-card-route", "View Route Details");
  }

  // compare.html: a small static route map inside each profile card
  async function initCompareMaps() {
    const origin = localStorage.getItem("smartCommute_routeOriginId");
    const destination = localStorage.getItem("smartCommute_routeDestId");
    const studentMode = localStorage.getItem("smartCommute_studentMode") === "true";
    const passenger_type = studentMode ? "student" : "regular";
    let data;
    try {
      data = await getJSON("/api/map/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ origin, destination, passenger_type }),
      });
    } catch (err) {
      console.warn("compare maps unavailable:", err);
      return;
    }
    for (const item of data.routes) {
      const id = item.route.profile.id;
      
      // Expose to window so modal can access it
      window.compareRouteDataMap = window.compareRouteDataMap || {};
      window.compareRouteDataMap[id] = item;
      
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
      L.tileLayer(TILES.dark, tileOpts("dark", false)).addTo(mini);
      const layer = L.geoJSON(item.geojson, { style: styleLine, pointToLayer }).addTo(mini);
      const b = item.geojson.bounds || layer.getBounds();
      keepSized(mini, el, () => { if (b) mini.fitBounds(b, { padding: [16, 16], maxZoom: 13 }); });
      if (b) mini.fitBounds(b, { padding: [16, 16], maxZoom: 13 });
    }
  }

  // compare.html: render map inside the modal
  window.renderModalMap = function(profileId) {
    const el = document.getElementById("modal-map");
    if (!el || !window.compareRouteDataMap || !window.compareRouteDataMap[profileId]) return;
    
    // Clear previous map instance if any
    if (el._leaflet_id) {
        el.outerHTML = el.outerHTML; // Removes the element and recreates it to destroy map
        // but wait, redefining innerHTML or just removing the map instance is better
    }
    const newEl = document.getElementById("modal-map");
    // Proper way to destroy leaflet map:
    if (window.currentModalMap) {
        window.currentModalMap.remove();
        window.currentModalMap = null;
    }

    const item = window.compareRouteDataMap[profileId];
    const map = L.map(newEl, { zoomControl: true, scrollWheelZoom: false }).setView(METRO_CENTER, 12);
    window.currentModalMap = map;
    window.currentModalGeoJSON = item.geojson;
    L.tileLayer(TILES.dark, tileOpts("dark", true)).addTo(map);
    const layer = L.geoJSON(item.geojson, { style: styleLine, pointToLayer }).addTo(map);
    const b = item.geojson.bounds || layer.getBounds();
    keepSized(map, newEl, () => { if (b) map.fitBounds(b, { padding: [30, 30], maxZoom: 14 }); });
    if (b) map.fitBounds(b, { padding: [30, 30], maxZoom: 14 });
    
    // Invalidate size after a slight delay to ensure modal is fully visible
    setTimeout(() => { map.invalidateSize(); if(b) map.fitBounds(b, { padding: [30, 30], maxZoom: 14 }); }, 100);
  };

  document.addEventListener("DOMContentLoaded", () => {
    if (typeof L === "undefined") return; // leaflet not on this page
    if (document.getElementById("network-map")) initNetworkMap();
    if (document.getElementById("location-map")) initLocationMap();
    if (document.getElementById("result-map")) initResultMap();
    if (document.querySelector(".compare-card-map")) initCompareMaps();
  });
})();
