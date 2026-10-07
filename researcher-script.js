const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// Re-mapped to match user side styles.css variables
const MODE_COLORS = { 
    "LRT-1": "#ef4444", 
    "LRT-2": "#a855f7", 
    "MRT-3": "#3b82f6", 
    "EDSA-Bus": "#10b981", 
    "Jeepney": "#f59e0b" 
};

const CRIT = {
    R: { label: "Flood risk", color: "var(--safest)" },      /* Red */
    P: { label: "Transfer",   color: "var(--convenient)" },  /* Green */
    T: { label: "Ridership",  color: "var(--uncrowded)" },   /* Blue */
    F: { label: "Fare",       color: "var(--cheapest)" },    /* Yellow */
};

const PROFILE_DOT = { 
    uncrowded: "#0d6efd", 
    cheapest: "#f59e0b", 
    safest: "#dc2626", 
    convenient: "#10b981" 
};
const DEFAULT_ANCHORS = [
    { id: 'monumento', name: 'Monumento Circle' },
    { id: 'sm_novaliches', name: 'SM City Novaliches' },
    { id: 'sm_north', name: 'SM North EDSA' },
    { id: 'cubao', name: 'Cubao Gateway' },
    { id: 'doroteo_jose', name: 'Doroteo Jose' },
    { id: 'shaw', name: 'Shaw Boulevard' },
    { id: 'antipolo', name: 'Antipolo LRT-2' },
    { id: 'pasig', name: 'Pasig Mega Market' },
    { id: 'pasay', name: 'Pasay EDSA-Taft' },
    { id: 'pitx', name: 'PITX' }
];
const DEFAULT_PROFILES = [
    { id: 'uncrowded', name: 'Uncrowded', priority: 'T', weights: { R: 0.16, P: 0.22, T: 0.52, F: 0.10 }, cr: 0.07 },
    { id: 'cheapest', name: 'Cheapest', priority: 'F', weights: { R: 0.16, P: 0.22, T: 0.10, F: 0.52 }, cr: 0.06 },
    { id: 'safest', name: 'Safest', priority: 'R', weights: { R: 0.52, P: 0.22, T: 0.16, F: 0.10 }, cr: 0.07 },
    { id: 'convenient', name: 'Convenient', priority: 'P', weights: { R: 0.16, P: 0.52, T: 0.10, F: 0.22 }, cr: 0.08 },
];
let PROFILES = [], BY_ID = {};
let map = null, animLayers = [];
let NETWORK_GJ = null;

function setConn(on) {
    const pill = $('status-pill');
    const label = $('status-text');
    
    // Toggle the classes
    pill.classList.toggle('online', on);
    pill.classList.toggle('offline', !on);
    
    // Update the label text
    label.innerText = on ? 'Online' : 'Offline';
}

function renderSOP(b) {
    const rm = b.sop2.rm_anova || {};
    // the four hypothesis tiles (mean cost reduction, mean jaccard, anova f, nodes delta)
    const tiles = document.querySelectorAll('.hyp-card .hc-value');
    if (tiles.length >= 4) {
        tiles[0].innerText = b.sop1.mean_reduction_pct + '%';
        tiles[1].innerText = b.sop2.mean_jaccard ?? '—';
        tiles[2].innerText = (rm.F ?? '—') + (rm.p_gg_corrected != null ? ` (p ${rm.p_gg_corrected})` : '');
        tiles[3].innerText = (b.sop3.fw_nodes_mean - b.sop3.bl_nodes_mean > 0 ? '+' : '')
            + Math.round((b.sop3.fw_nodes_mean - b.sop3.bl_nodes_mean) * 10) / 10;
    }
    if ($('m-obs')) $('m-obs').innerText = b.observations;
    // the verdict box follows the live results instead of a fixed label: h1
    // is two-sided, so each sop counts as supported when its test rejects,
    // and the direction is spelled out where it matters
    const box = document.querySelector('.hypothesis-box');
    const status = document.querySelector('.hypothesis-box .hb-status');
    if (box && status) {
        const held = [['SOP1', b.sop1.supported], ['SOP2', b.sop2.supported], ['SOP3', b.sop3.supported]].filter(x => x[1]);
        const all = held.length === 3;
        box.classList.toggle('supported', all);
        status.innerText = all ? '✓ Supported' : held.length
            ? `Partly supported · ${held.map(x => x[0]).join(', ')}` : 'Not supported';
        if (b.sop3.direction === 'framework_expands_more') status.title = 'SOP3 differs significantly, but the framework expands more nodes than the baseline';
    }
}

function renderAhp(profileId, isEmpty = false) {
    const p = PROFILES.find(x => x.id === profileId) || PROFILES[0];
    if (!p) return;
    
    // 1. Set the header to a neutral placeholder when empty
    const ahpHeader = document.getElementById('ahp-profile-name');
    if (ahpHeader) {
        ahpHeader.innerText = isEmpty ? '—' : p.name + ' Profile';
    }

    const max = Math.max(...Object.values(p.weights));
    let html = ["R","P","T","F"].map(k => {
        const w = p.weights[k] || 0;
        
        // 2. Only apply the dominant styling if it is NOT the empty state
        const dom = !isEmpty && (k === p.priority); 
        
        const displayVal = isEmpty ? "—" : w.toFixed(2);
        const widthPct = isEmpty ? "0" : (w / max * 100).toFixed(0);
        
        const keyColorStyle = dom ? `style="color: ${CRIT[k].color} !important;"` : '';
        
        return `<div class="ahp-row ${dom ? 'dominant' : ''}">
            <div class="ahr-head">
                <span class="ahr-name"><span class="ahr-key" ${keyColorStyle}>W_${k}</span>${CRIT[k].label}</span>
                <span class="ahr-val">${displayVal}</span>
            </div>
            <div class="ahr-bar"><span class="ahr-bar-fill" style="width:${widthPct}%;background:${CRIT[k].color};opacity:${dom ? 1 : 0.4}"></span></div>
        </div>`;
    }).join('');
    
    const crDisplay = isEmpty ? "—" : `CR = ${(p.cr || 0.07).toFixed(2)} ${(p.cr || 0.07) < 0.1 ? '✓' : ''}`;
    html += `<div class="ahp-cr"><span class="ahcr-l">Consistency Ratio</span><span class="ahcr-v">${crDisplay}</span></div>`;
    // say plainly where the weights come from: the survey is not in yet, so
    // the engine runs the real ahp pipeline on synthetic respondents
    if (!isEmpty && /simulated|mock/i.test(p.weights_source || '')) {
        const counts = p.n_accepted ? ` · ${p.n_accepted} of ${p.n_respondents} simulated respondents passed CR < 0.10` : '';
        html += `<div class="ahp-src">Synthetic data${counts}. Replaced once the commuter survey is complete.</div>`;
    }
    $('ahp-bars').innerHTML = html;
}

function renderModels(data) {
    const el = $('model-list');
    if (!el) return;
    // live metrics from /api/ml-metrics; fall back to placeholders only if
    // the payload is missing so the panel never sees invented numbers
    const models = (data && data.models && data.models.length) ? data.models : [
        { key:'lstm', name:'LSTM · Ridership', rmse:null, detail:'metrics unavailable' },
        { key:'rfr', name:'RFR · Flood Risk', rmse:null, detail:'metrics unavailable' }
    ];
    el.innerHTML = models.map(m => {
        const ic = m.key === 'rfr' ? 'R' : m.key === 'busway' ? 'B' : m.key === 'lrt2' ? '2' : 'L';
        const cls = m.key === 'rfr' ? 'rfr' : 'lstm';
        const rmse = m.rmse != null ? `RMSE ${m.rmse}` : 'RMSE —';
        return `<div class="model-card ${cls}">
            <div class="mc-icon">${ic}</div>
            <div class="mc-body">
                <div class="mc-name">${m.name}</div>
                <div class="mc-meta">${rmse} · ${m.detail || ''}</div>
            </div>
            <div class="mc-status live">${m.status === 'trained' ? 'TRAINED' : 'LIVE'}</div>
        </div>`;
    }).join('');
}

function initMap() {
    map = L.map('research-map', { zoomControl:false, scrollWheelZoom:false }).setView([14.6,121.02], 11);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    // esri dark canvas: keyless (carto now watermarks keyless requests); native tiles to z16
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', { maxZoom:19, maxNativeZoom:16, attribution:'Esri, HERE, Garmin, &copy; OpenStreetMap contributors' }).addTo(map);
    // one download shared with init(), which reads the same geojson for node positions
    NETWORK_GJ = fetch('/api/map/network').then(r => r.json());
    // base layer: every jeepney route as an orange line (the jeepney mode
    // colour), rail and busway corridors in mode colours, and the ten anchors
    // only - the virtual stops are what the router walks through, not
    // something to draw
    fetch('/api/map/routes').then(r => r.json()).then(routes => {
        L.geoJSON(routes, {
            style: () => ({ color: MODE_COLORS.Jeepney, weight: 2, opacity: 0.6 }),
            onEachFeature: (f, layer) => { if (f.properties.route) layer.bindTooltip(f.properties.route, { sticky: true }); },
        }).addTo(map);
    }).catch(() => {});
    NETWORK_GJ.then(gj => {
        const corridors = (gj.features || []).filter(f => f.geometry.type === 'LineString' && f.properties.mode !== 'Jeepney');
        L.geoJSON({ type: 'FeatureCollection', features: corridors }, {
            style: f => ({ color: MODE_COLORS[f.properties.mode] || '#2b3550', weight: 3, opacity: 0.7 }),
        }).addTo(map);
        // no station dots here: each replay marks only its own origin and
        // destination, not every station the route passes through
        if (gj.bounds) map.fitBounds(gj.bounds, { padding:[40,40], maxZoom:13 });
        setTimeout(() => map.invalidateSize(), 250);
    }).catch(() => {});
    if (window.ResizeObserver) new ResizeObserver(() => map.invalidateSize()).observe($('research-map'));
}

function renderDecomp(d, isEmpty = false) {
    // real numbers from the a* run: each criterion's normalized value averaged
    // over the route, weighted by leg time (the N' terms of the cost equation)
    const legs = (d && d.decomposition) || [];
    const time = legs.reduce((s, l) => s + (l.base_time || 0), 0);
    if (!legs.length || !time) isEmpty = true;
    const vals = {};
    ["R","T","P","F"].forEach(k => {
        vals[k] = isEmpty ? 0 : legs.reduce((s, l) => s + (l.base_time || 0) * (l[k] || 0), 0) / time;
    });
    const max = Math.max(...Object.values(vals)) || 1;
    let html = ["R","T","P","F"].map(k => {
        const w = vals[k];
        const displayVal = isEmpty ? "—" : w.toFixed(2);
        const widthPct = isEmpty ? "0" : (w / max * 100).toFixed(0);
        
        return `<div class="cd-row">
            <div class="cdr-head">
                <span class="cdr-name"><span class="cdr-key">${k}'</span>${CRIT[k].label}</span>
                <span class="cdr-val">${displayVal}</span>
            </div>
            <div class="cdr-bar"><span class="cdr-bar-fill" style="width:${widthPct}%;background:${CRIT[k].color};"></span></div>
        </div>`;
    }).join('');
    $('cd-legs').innerHTML = html;
    $('cd-total').innerText = isEmpty ? "—" : Math.round(d.total_cost * 100) / 100;
}

document.addEventListener('click', (e) => {
    const btn = e.target.closest('.help');
    if (btn) {
        e.stopPropagation();
        const pop = btn.parentElement.querySelector('.help-pop');
        const open = pop && pop.classList.contains('show');
        document.querySelectorAll('.help-pop.show').forEach(p => p.classList.remove('show'));
        document.querySelectorAll('.help.on').forEach(x => x.classList.remove('on'));
        if (pop && !open) { pop.classList.add('show'); btn.classList.add('on'); }
        return;
    }
    document.querySelectorAll('.help-pop.show').forEach(p => p.classList.remove('show'));
    document.querySelectorAll('.help.on').forEach(x => x.classList.remove('on'));
});

function buildQueryList(anchors, profiles) {
    const container = $('query-list');
    if (!container) return;
    const pairs = [];
    for (let i = 0; i < anchors.length; i++) {
        for (let j = i + 1; j < anchors.length; j++) {
            pairs.push([anchors[i], anchors[j]]);
        }
    }
    const items = [];
    pairs.forEach(([origin, destination]) => {
        profiles.forEach((profile) => {
            items.push({
                od: `${origin.name} → ${destination.name}`,
                oid: origin.id, did: destination.id,
                profile: profile.id,
                profileName: profile.name,
            });
        });
    });
    // data-idx is the observation number on the timeline (45 od pairs x 4 profiles)
    container.innerHTML = items.map((item, idx) => `
        <div class="query-log-item" data-profile="${item.profile}" data-od="${item.od.toLowerCase()}"
             data-oid="${item.oid}" data-did="${item.did}" data-idx="${idx}">
            <div class="qli-top">
                <div class="qli-od">${item.od}</div>
                <div class="qli-profile ${item.profile}"><span class="qlip-dot"></span>${item.profileName}</div>
            </div>
            <div class="qli-bottom">click to run · a* playback</div>
        </div>
    `).join('');
    // clicks are handled by one delegated listener (initQueryLogClicks), which
    // runs the real a* and animates the expansion through activateQuery
}

function showToast(message) {
    const existing = document.querySelector('.custom-toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'custom-toast';
    toast.innerHTML = `<div class="custom-toast-icon">!</div><div>${message}</div>`;
    document.body.appendChild(toast);
    
    toast.offsetHeight;
    toast.classList.add('show');
    
    setTimeout(() => {
        if(toast.parentElement) {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }
    }, 3000);
}

function filterQueryLog() {
    const originFilter = $('query-filter-origin') ? $('query-filter-origin').value : '';
    let destFilter = $('query-filter-dest') ? $('query-filter-dest').value : '';
    
    if (originFilter && destFilter && originFilter === destFilter) {
        showToast("Starting point and destination cannot be the same.");
        $('query-filter-dest').value = '';
        destFilter = '';
    }

    const items = document.querySelectorAll('#query-list .query-log-item');
    
    items.forEach(item => {
        const itemOrigin = item.dataset.oid;
        const itemDest = item.dataset.did;
        
        let matchesOrigin = !originFilter || itemOrigin === originFilter;
        let matchesDest = !destFilter || itemDest === destFilter;
        
        item.style.display = (matchesOrigin && matchesDest) ? '' : 'none';
    });
}

let PLAY_TOKEN = 0;

// an arrow that rides the winning route from origin to destination. it walks
// the same waypoints the line is drawn from, so it follows every bend of the
// real track, and it turns to face the direction of travel. timers, not
// requestAnimationFrame, so the replay keeps moving when the tab is hidden.
function travel(route, ms, token, color) {
    if (!route || route.length < 2) return Promise.resolve(true);
    const cum = [0];
    for (let i = 1; i < route.length; i++) {
        const a = route[i - 1], b = route[i];
        const kx = Math.cos(((a[0] + b[0]) / 2) * Math.PI / 180);
        cum.push(cum[i - 1] + Math.hypot((b[1] - a[1]) * kx, b[0] - a[0]));
    }
    const total = cum[cum.length - 1];
    if (!total) return Promise.resolve(true);
    if (token !== PLAY_TOKEN) return Promise.resolve(false);
    const icon = L.divIcon({ className: 'route-traveler', iconSize: [26, 26], iconAnchor: [13, 13],
        html: `<div class="rt-arrow"><svg viewBox="0 0 24 24" width="26" height="26"><path d="M3 4 L22 12 L3 20 L8 12 Z" fill="#fff" stroke="${color}" stroke-width="2.4" stroke-linejoin="round"/></svg></div>` });
    const marker = L.marker(route[0], { icon, interactive: false, keyboard: false, zIndexOffset: 1200 }).addTo(map);
    animLayers.push(marker);
    const t0 = performance.now();
    let seg = 1;
    return new Promise(resolve => {
        const tick = () => {
            if (token !== PLAY_TOKEN) { try { map.removeLayer(marker); } catch (e) {} resolve(false); return; }
            const f = Math.min(1, (performance.now() - t0) / ms);
            const target = f * total;
            while (seg < cum.length - 1 && cum[seg] < target) seg++;
            const a = route[seg - 1], b = route[seg];
            const span = cum[seg] - cum[seg - 1];
            const u = span ? (target - cum[seg - 1]) / span : 1;
            marker.setLatLng([a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u]);
            const pa = map.latLngToLayerPoint(a), pb = map.latLngToLayerPoint(b);
            const el = marker.getElement() && marker.getElement().querySelector('.rt-arrow');
            if (el && (pa.x !== pb.x || pa.y !== pb.y)) el.style.transform = `rotate(${Math.atan2(pb.y - pa.y, pb.x - pa.x)}rad)`;
            if (f < 1) setTimeout(tick, 16);
            else { try { map.removeLayer(marker); } catch (e) {} resolve(true); }
        };
        tick();
    });
}

// opts.fast is the timeline replay: same real a* run, shorter animation.
// resolves true when the playback ran to the end, false if it was superseded
// by another selection or the engine could not be reached.
// a* search view (toggle on the map): the states each run expanded, the
// framework in its profile colour and the distance baseline in white, plus the
// baseline's own route dashed. drawn on one canvas layer so it stays light.
let SEARCH_MODE = 'off', LAST_INSPECT = null, searchLayers = [], searchCanvas = null;
function clearSearch() { searchLayers.forEach(l => { try { map.removeLayer(l); } catch (e) {} }); searchLayers = []; }
function drawSearch(d, profileId) {
    clearSearch();
    if (!d || SEARCH_MODE === 'off' || !map) return;
    searchCanvas = searchCanvas || L.canvas({ padding: 0.3 });
    const dots = (ids, color) => (ids || []).forEach(id => {
        const a = BY_ID[id];
        if (a) searchLayers.push(L.circleMarker([a.lat, a.lng], { renderer: searchCanvas, radius: 2.5, stroke: false, fillColor: color, fillOpacity: 0.55, interactive: false }).addTo(map));
    });
    if (SEARCH_MODE === 'baseline' || SEARCH_MODE === 'both') {
        dots(d.baseline_expanded_order, '#ffffff');
        (d.baseline_legs || []).forEach(leg => {
            const a = BY_ID[leg.from_id], b = BY_ID[leg.to_id];
            const pts = leg.points || ((a && b) ? [[a.lat, a.lng], [b.lat, b.lng]] : null);
            if (pts) searchLayers.push(L.polyline(pts, { color: '#ffffff', weight: 3, opacity: 0.85, dashArray: '6 6', interactive: false }).addTo(map));
        });
    }
    if (SEARCH_MODE === 'framework' || SEARCH_MODE === 'both') dots(d.expanded_order, PROFILE_DOT[profileId] || '#0071e3');
    const note = $('search-note');
    if (note) note.innerText = SEARCH_MODE === 'off' ? '' :
        `framework ${d.expanded_nodes} · baseline ${d.baseline_nodes} states expanded`;
}
function initSearchToggle() {
    document.querySelectorAll('.search-toggle button').forEach(btn => btn.addEventListener('click', () => {
        SEARCH_MODE = btn.dataset.mode;
        document.querySelectorAll('.search-toggle button').forEach(b => b.classList.toggle('on', b === btn));
        if (LAST_INSPECT) drawSearch(LAST_INSPECT.d, LAST_INSPECT.profile);
        else if (SEARCH_MODE !== 'off') { const n = $('search-note'); if (n) n.innerText = 'pick a query from the log first'; }
    }));
}

async function playInspect(q, opts = {}) {
    if (!q || !map) return false;
    const fast = !!opts.fast;
    const token = ++PLAY_TOKEN;
    animLayers.forEach(l => { try { map.removeLayer(l); } catch (e) {} });
    animLayers = [];
    clearSearch();
    let d;
    try {
        const res = await fetch('/api/inspect', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ origin: q.origin, destination: q.destination, profile: q.profile }) });
        d = await res.json();
    } catch (e) { return false; }
    if (token !== PLAY_TOKEN || !d || !d.found) return false;
    if ($('ov-origin')) $('ov-origin').innerText = d.origin || q.origin;
    if ($('ov-dest')) $('ov-dest').innerText = d.destination || q.destination;
    renderDecomp(d);
    LAST_INSPECT = { d, profile: q.profile };
    clearSearch();
    // frame the route before it draws, so nothing animates outside the view
    const frame = (d.path || []).map(id => BY_ID[id]).filter(Boolean).map(a => [a.lat, a.lng]);
    if (frame.length > 1) map.fitBounds(frame, { padding: [60, 60], maxZoom: 14, animate: !fast });
    // this page draws only the winning route and its arrow. the search effort
    // is reported as numbers in the counters (nodes expanded vs the baseline);
    // drawing every expanded state here made the 180-observation replay lag
    // the route is bent along the real track where the gateway attached shape
    // waypoints (leg.points). the same waypoints are collected into one line
    // for the travelling arrow.
    const legs = d.decomposition || [];
    const route = [];
    const lchunk = Math.max(1, Math.ceil(legs.length / (fast ? 8 : 60)));
    for (let i = 0; i < legs.length; i += lchunk) {
        if (token !== PLAY_TOKEN) return false;
        for (const leg of legs.slice(i, i + lchunk)) {
            const a = BY_ID[leg.from_id], b = BY_ID[leg.to_id];
            const pts = leg.points || ((a && b) ? [[a.lat, a.lng], [b.lat, b.lng]] : null);
            if (!pts) continue;
            animLayers.push(L.polyline(pts, { color: MODE_COLORS[leg.mode] || '#0071e3', weight: 6, opacity: 0.95 }).addTo(map));
            pts.forEach(p => {
                const last = route[route.length - 1];
                if (!last || last[0] !== p[0] || last[1] !== p[1]) route.push(p);
            });
        }
        await sleep(fast ? 12 : 30);
    }
    // a newer selection may have started during that last pause: stop here so
    // this run cannot add its markers, counters or arrow on top of it
    if (token !== PLAY_TOKEN) return false;
    const o = BY_ID[d.origin_id], de = BY_ID[d.destination_id];
    if (o) animLayers.push(L.circleMarker([o.lat, o.lng], { radius: 8, color: '#fff', fillColor: '#30d158', fillOpacity: 1, weight: 2 }).addTo(map).bindTooltip('Origin'));
    if (de) animLayers.push(L.circleMarker([de.lat, de.lng], { radius: 8, color: '#fff', fillColor: '#ff3b30', fillOpacity: 1, weight: 2 }).addTo(map).bindTooltip('Destination'));
    // real counters: nodes expanded vs the baseline run, execution ms, g at goal
    if ($('ov-nodes')) $('ov-nodes').innerText = d.expanded_nodes;
    if ($('ov-nodes-delta')) $('ov-nodes-delta').innerText = `vs ${d.baseline_nodes} baseline`;
    if ($('ov-ms')) $('ov-ms').innerHTML = `${d.query_ms}<span class="ovc-unit">ms</span>`;
    if ($('ov-cost')) $('ov-cost').innerText = Math.round(d.total_cost * 10) / 10;
    drawSearch(d, q.profile);
    if (q.el) q.el.querySelector('.qli-bottom').innerText = `${d.expanded_nodes} nodes · ${d.query_ms} ms · vs ${d.baseline_nodes} baseline`;
    const arrived = await travel(route, fast ? 800 : 1800, token, PROFILE_DOT[q.profile] || '#0071e3');
    if (arrived && fast) await sleep(250);
    return arrived && token === PLAY_TOKEN;
}

// ---- timeline: the play button replays the whole benchmark run ----
// position = how many observations have played. segments before it are lit.
const TL = { playing: false, index: 0, run: 0 };
const tlItems = () => Array.from(document.querySelectorAll('#query-list .query-log-item'));
const tlSegs = () => Array.from(document.querySelectorAll('#timeline-segments .tl-seg'));

function paintTimeline(position, label, current = -1) {
    const segs = tlSegs();
    const total = tlItems().length || segs.length;
    segs.forEach((s, i) => {
        s.classList.toggle('completed', i < position);
        s.classList.toggle('current', i === current);
    });
    const meta = document.querySelector('.timeline-meta');
    if (meta) meta.innerHTML = `<strong>${position}</strong> / ${total} <span style="color: var(--rule); margin: 0 4px;">·</span> ${label}`;
    const cursor = document.querySelector('.timeline-cursor');
    if (cursor) cursor.style.left = (total ? position / total * 100 : 0) + '%';
    const btn = document.querySelector('.play-btn');
    if (btn) {
        btn.classList.toggle('playing', TL.playing);
        btn.setAttribute('aria-label', TL.playing ? 'Pause' : 'Play');
    }
}

async function runTimeline() {
    const total = tlItems().length;
    if (!total) return;
    if (TL.index >= total) TL.index = 0;   // a finished run replays from observation 1
    TL.playing = true;
    const run = ++TL.run;
    let failed = false;
    while (TL.playing && run === TL.run && TL.index < total) {
        // read the list fresh each step: init() rebuilds it once the api answers
        const i = TL.index, item = tlItems()[i];
        if (!item) break;
        if (item.style.display === 'none') { TL.index = i + 1; continue; }   // respect the od filter
        paintTimeline(i, 'Playing', i);
        // keep the running query in view inside the log without scrolling the page
        const box = $('query-list');
        if (box) box.scrollTop += item.getBoundingClientRect().top - box.getBoundingClientRect().top - box.clientHeight / 2 + item.clientHeight / 2;
        // a throw inside one observation must end the run cleanly, not leave
        // the button stuck on playing
        let ok = false;
        try { ok = await activateQuery(item, { fast: true }); } catch (err) { ok = false; }
        if (run !== TL.run) return;        // a manual selection took over the timeline
        if (!ok) { failed = true; break; }   // engine unreachable: stop, do not spin through 180 failures
        TL.index = i + 1;
    }
    TL.playing = false;
    // on a failure the index stays on the observation that did not run, so
    // play retries it, and that observation (the selected row) is outlined
    const done = !failed && TL.index >= total;
    paintTimeline(TL.index, failed ? 'Engine unreachable' : done ? 'Complete' : 'Paused',
        failed ? TL.index : done ? -1 : TL.index - 1);
}

function initTimelinePlay() {
    const btn = document.querySelector('.play-btn');
    if (btn) btn.addEventListener('click', () => {
        if (TL.playing) {
            // pause after the observation on screen finishes, so the map is never left half drawn
            TL.playing = false;
            paintTimeline(TL.index, 'Pausing…', TL.index);
        } else {
            runTimeline();
        }
    });
    // a segment is an observation: clicking it jumps the dashboard to that query
    const track = $('timeline-segments');
    if (track) track.addEventListener('click', (e) => {
        const seg = e.target.closest('.tl-seg');
        const item = seg && tlItems()[tlSegs().indexOf(seg)];
        if (item) item.click();
    });
}

// one entry point for a real click and for the timeline replay
function activateQuery(item, opts = {}) {
    syncSelectionUI(item);
    const q = { origin: item.dataset.oid, destination: item.dataset.did, profile: item.dataset.profile, el: item };
    return playInspect(q, opts);
}

function buildTimeline() {
    const container = document.getElementById('timeline-segments');
    if (!container) return;
    container.innerHTML = '';
    const profiles = ['uncrowded', 'cheapest', 'safest', 'convenient'];
    for (let i = 0; i < 180; i++) {
        const seg = document.createElement('div');
        seg.className = 'tl-seg completed ' + profiles[i % 4];
        seg.title = `Observation ${i + 1}`;
        container.appendChild(seg);
    }
}

function initRunToggle() {
    const button = document.querySelector('.run-toggle');
    const section = document.getElementById('run-select-section');
    const items = document.querySelectorAll('#run-select-section .rs-item');
    if (!button || !section) return;
    button.addEventListener('click', () => {
        const expanded = button.getAttribute('aria-expanded') === 'true';
        button.setAttribute('aria-expanded', String(!expanded));
        section.classList.toggle('open', !expanded);
    });
    items.forEach((item) => {
        item.addEventListener('click', () => {
            items.forEach((row) => row.classList.remove('active'));
            item.classList.add('active');
            document.querySelector('.active-run-title').innerText = item.dataset.run;
            document.querySelector('.active-run-sub').innerText = item.querySelector('.rs-sub').innerText;
            section.classList.remove('open');
            button.setAttribute('aria-expanded', 'false');
        });
    });
}

function initProfileLegend() {
    const items = document.querySelectorAll('.ov-legend .leg-item');
    items.forEach((item) => {
        item.addEventListener('click', () => {
            // the locked button is the profile already on screen
            if (item.getAttribute('data-locked') === 'true') return;
            // switch to the same trip under the clicked profile. it goes through
            // the query log click, so it stops a running replay, runs the real
            // a* and moves the highlight (only one profile is ever selected)
            const current = document.querySelector('.query-log-item.active');
            if (!current) return;
            const target = document.querySelector(
                `.query-log-item[data-oid="${current.dataset.oid}"][data-did="${current.dataset.did}"][data-profile="${item.dataset.profile}"]`);
            if (!target) return;
            target.click();
            const box = $('query-list');
            if (box) box.scrollTop += target.getBoundingClientRect().top - box.getBoundingClientRect().top - box.clientHeight / 2 + target.clientHeight / 2;
        });
    });
}

function initQueryLogClicks() {
    const queryList = $('query-list');
    const legendBox = document.querySelector('.ov-legend');
    
    // 0a. Clear any pre-selected buttons from the HTML on load
    document.querySelectorAll('.ov-legend .leg-item').forEach(btn => {
        btn.classList.remove('selected');
        btn.setAttribute('aria-pressed', 'false');
    });
    
    // 0b. Lock the entire legend box until a query is clicked
    if (legendBox) {
        legendBox.classList.add('disabled');
    }

    if (!queryList) return;

    // one delegated listener: a real click stops the replay and takes over
    queryList.addEventListener('click', (e) => {
        const clickedItem = e.target.closest('.query-log-item');
        if (!clickedItem) return;
        TL.playing = false;
        TL.run++;
        const idx = Number(clickedItem.dataset.idx);
        if (!Number.isNaN(idx)) {
            TL.index = idx + 1;
            paintTimeline(idx + 1, 'Paused', idx);
        }
        activateQuery(clickedItem);
    });
}

// everything the dashboard shows for a selected query, except the map
// playback: legend lock, od pills, ahp weights. the cost decomposition
// fills in with the real a* numbers as soon as the inspect response lands.
function syncSelectionUI(item) {
    const legendBox = document.querySelector('.ov-legend');
    if (legendBox) legendBox.classList.remove('disabled');

    document.querySelectorAll('.query-log-item.active').forEach(x => x.classList.remove('active'));
    item.classList.add('active');

    const activeProfile = item.dataset.profile;
    document.querySelectorAll('.ov-legend .leg-item').forEach(btn => {
        btn.removeAttribute('data-locked');
        btn.classList.remove('selected');
        btn.setAttribute('aria-pressed', 'false');
    });
    const targetBtn = document.querySelector(`.ov-legend .leg-item[data-profile="${activeProfile}"]`);
    if (targetBtn) {
        targetBtn.classList.add('selected');
        targetBtn.setAttribute('aria-pressed', 'true');
        targetBtn.setAttribute('data-locked', 'true'); // Prevents toggling off
    }

    const odParts = item.querySelector('.qli-od').innerText.split(' → ');
    if (odParts.length === 2) {
        const originPill = document.getElementById('cd-origin');
        const destPill = document.getElementById('cd-dest');
        if (originPill) originPill.innerText = odParts[0];
        if (destPill) destPill.innerText = odParts[1];
    }

    // blank the decomposition until this query's own numbers arrive, so the
    // panel never shows the previous route's values under the new od pills
    renderDecomp(null, true);
    renderAhp(activeProfile, false);
}

async function init() {
    buildTimeline();
    initMap();
    initRunToggle();
    initProfileLegend();
    PROFILES = DEFAULT_PROFILES;
    buildQueryList(DEFAULT_ANCHORS, DEFAULT_PROFILES);
    initQueryLogClicks();
    initTimelinePlay();
    initImportExport();
    initSearchToggle();
    
    // Set to empty placeholders on initial load
    renderAhp('safest', true);
    renderDecomp(null, true);
    renderModels({});
    const originFilter = $('query-filter-origin');
    const destFilter = $('query-filter-dest');
    const clearBtn = $('query-filter-clear');
    if (originFilter) originFilter.addEventListener('change', filterQueryLog);
    if (destFilter) destFilter.addEventListener('change', filterQueryLog);
    
    if (clearBtn) {
        clearBtn.addEventListener('click', (e) => {
            e.preventDefault();
            if (originFilter) originFilter.value = '';
            if (destFilter) destFilter.value = '';
            filterQueryLog();
        });
    }
    
    try {
        const [bench, ml, anchors, profiles] = await Promise.all([
            fetch('/api/benchmark').then(r => r.json()),
            fetch('/api/ml-metrics').then(r => r.json()),
            fetch('/api/map/anchors').then(r => r.json()),
            fetch('/api/map/profiles').then(r => r.json()),
        ]);
        // with the engine down the gateway answers 502 with an error object, not
        // a list. stop here so the page keeps its offline defaults
        if (!Array.isArray(anchors) || !Array.isArray(profiles)) throw new Error('engine unreachable');
        PROFILES = profiles;
        BY_ID = Object.fromEntries(anchors.map(a => [a.id, a]));
        // the playback needs every node position, virtual jeepney stops included
        NETWORK_GJ.then(gj => {
            (gj.features || []).forEach(f => {
                if (f.geometry && f.geometry.type === 'Point') {
                    const p = f.properties || {};
                    if (p.id && !BY_ID[p.id]) BY_ID[p.id] = { id: p.id, name: p.name, lat: f.geometry.coordinates[1], lng: f.geometry.coordinates[0] };
                }
            });
        }).catch(() => {});
        setConn(true);
        renderSOP(bench);
        renderModels(ml);
        
        // Keep it empty even after API fetch completes
        renderAhp('safest', true);
        
        buildQueryList(anchors.slice(0, 10), profiles.slice(0, 4));
    } catch (err) {
        setConn(false);
    }
}
init();

// ---- import and export ----
// export: the 360-row benchmark log as csv, and a pdf report that answers the
// three sops. import: a benchmark log csv in the same format the export makes;
// the engine checks it and works out the sop answers the log supports.
let IMPORTED = null;   // { csv, filename } of the last imported log

const esc = (s) => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmtP = (p) => (p < 0.001 ? '&lt; 0.001' : Number(p).toFixed(4));
const today = () => new Date().toISOString().slice(0, 10);

function saveBlob(blob, name) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
}

async function errorText(r, fallback) {
    try {
        const j = await r.json();
        if (typeof j.detail === 'string') return j.detail;
        if (j.error) return j.error;
    } catch (e) { /* not json */ }
    return fallback;
}

async function downloadFile(url, name, btn, init) {
    const label = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = 'Preparing…'; }
    try {
        const r = await fetch(url, init);
        if (!r.ok) throw new Error(await errorText(r, 'the engine did not answer'));
        saveBlob(await r.blob(), name);
    } catch (err) {
        showToast('Export failed: ' + esc(err.message));
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = label; }
    }
}

function closeImportPanel() {
    const o = document.querySelector('.imp-overlay');
    if (o) o.remove();
    document.removeEventListener('keydown', importKeys);
}

function importKeys(e) { if (e.key === 'Escape') closeImportPanel(); }

function showImportResult(d) {
    closeImportPanel();
    const dir = (x) => x === 'framework_higher' ? 'higher' : x === 'framework_lower' ? 'lower' : 'equal';
    const s1 = (d.sop1 || []).map(r => `
        <tr><td>${esc(r.profile[0].toUpperCase() + r.profile.slice(1))}</td><td>${esc(r.criterion)}</td>
        <td>${r.mean_baseline.toFixed(3)}</td><td>${r.mean_framework.toFixed(3)}</td><td>${fmtP(r.p)}</td>
        <td>${r.significant ? 'Yes' : 'No'}</td><td>${dir(r.direction)}</td></tr>`).join('');
    const s2 = d.sop2, a = s2.rm_anova_travel_time, n = d.sop3.nodes, ms = d.sop3.exec_ms;
    const ratio = ms.mean_baseline > 0 ? (ms.mean_framework / ms.mean_baseline).toFixed(1) : '–';
    const warn = (d.warnings || []).map(w => `<div class="imp-warn">${esc(w)}</div>`).join('');
    const o = document.createElement('div');
    o.className = 'imp-overlay';
    o.innerHTML = `
      <div class="imp-card" role="dialog" aria-modal="true" aria-label="Imported benchmark log">
        <div class="imp-head">
          <div>
            <div class="imp-eyebrow">Imported benchmark log</div>
            <div class="imp-title">${esc(d.filename)}</div>
            <div class="imp-sub">${d.rows} rows · ${d.od_pairs} origin and destination pairs · ${d.profiles.length} profiles</div>
          </div>
          <button class="imp-x" type="button" aria-label="Close">×</button>
        </div>
        ${warn}
        <h4>SOP 1 · each profile against the distance baseline</h4>
        <table class="imp-table"><thead><tr><th>Profile</th><th>Criterion</th><th>Baseline</th><th>Framework</th><th>p</th><th>p &lt; 0.05</th><th>Framework</th></tr></thead><tbody>${s1}</tbody></table>
        <p class="imp-note">Crowding and fare are the same measures as the live test. Flood risk uses the worst segment and Convenient uses the number of transfers, because the log does not store the mean flood risk or the transfer friction.</p>
        <h4>SOP 2 · different routes across the profiles</h4>
        <p>${s2.pairs_with_variance} of ${d.od_pairs} pairs (${s2.pct_with_variance}%) have at least two different routes, ${s2.mean_distinct_routes} routes per pair on average.${a ? ` RM-ANOVA on travel time: F ${a.F}, corrected p ${fmtP(a.p_decision)}.` : ''}</p>
        <h4>SOP 3 · search space</h4>
        <p>Nodes expanded: baseline ${n.mean_baseline.toFixed(1)}, framework ${n.mean_framework.toFixed(1)}, p ${fmtP(n.p)}. Execution time: the framework takes about ${ratio} times as long.</p>
        <div class="imp-actions">
          <button class="imp-btn ghost imp-close" type="button">Close</button>
          <button class="imp-btn imp-pdf" type="button">Download PDF report of this file</button>
        </div>
      </div>`;
    document.body.appendChild(o);
    o.addEventListener('click', (e) => { if (e.target === o) closeImportPanel(); });
    o.querySelector('.imp-x').addEventListener('click', closeImportPanel);
    o.querySelector('.imp-close').addEventListener('click', closeImportPanel);
    const pdfBtn = o.querySelector('.imp-pdf');
    pdfBtn.addEventListener('click', () => {
        if (!IMPORTED) return;
        const base = IMPORTED.filename.replace(/\.csv$/i, '').replace(/[^\w.-]+/g, '_');
        downloadFile('/api/benchmark/import/report', `${base}_report.pdf`, pdfBtn, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(IMPORTED),
        });
    });
    document.addEventListener('keydown', importKeys);
}

function initImportExport() {
    const imp = $('btn-import'), file = $('import-file');
    const csvBtn = $('btn-export-csv'), pdfBtn = $('btn-export-pdf');
    if (csvBtn) csvBtn.addEventListener('click', () =>
        downloadFile('/api/benchmark/log?format=csv', `smartcommuteph_benchmark_log_${today()}.csv`, csvBtn));
    if (pdfBtn) pdfBtn.addEventListener('click', () =>
        downloadFile('/api/benchmark/report', `smartcommuteph_benchmark_report_${today()}.pdf`, pdfBtn));
    if (!imp || !file) return;
    imp.addEventListener('click', () => { file.value = ''; file.click(); });
    file.addEventListener('change', async () => {
        const f = file.files && file.files[0];
        if (!f) return;
        if (f.size > 2000000) { showToast('That file is over 2 MB. Choose a benchmark log CSV made with Export CSV.'); return; }
        const label = imp.textContent;
        imp.disabled = true;
        imp.textContent = 'Reading…';
        try {
            const text = await f.text();
            const r = await fetch('/api/benchmark/import', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ csv: text, filename: f.name }),
            });
            if (!r.ok) throw new Error(await errorText(r, 'the engine could not read the file'));
            IMPORTED = { csv: text, filename: f.name };
            showImportResult(await r.json());
        } catch (err) {
            showToast('Import failed: ' + esc(err.message));
        } finally {
            imp.disabled = false;
            imp.textContent = label;
        }
    });
}
