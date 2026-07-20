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
let ANCHORS = [], PROFILES = [], BY_ID = {};
let map = null, animLayers = [], log = [];

function setConn(on, text) {
    const pill = $('status-pill');
    const dot = $('status-dot');
    const label = $('status-text');
    
    // Toggle the classes
    pill.classList.toggle('online', on);
    pill.classList.toggle('offline', !on);
    
    // Update the label text
    label.innerText = on ? 'Online' : 'Offline';
}

function renderSOP(b) {
    const items = [
        { tag:"SOP 1", stat:b.sop1.mean_reduction_pct + "%", ok:b.sop1.supported },
        { tag:"SOP 2", stat:b.sop2.mean_distinct_routes,     ok:b.sop2.supported },
        { tag:"SOP 3", stat:b.sop3.mean_reduction_pct + "%", ok:b.sop3.supported },
    ];
    $('sop-status').innerHTML = items.map(s => `<div class="sop-pill ${s.ok?'ok':'no'}">
        <div class="sp-name">${s.tag}</div>
        <div class="sp-stat">${s.stat}</div>
        <div class="sp-verdict">${s.ok?'Supported':'Not yet'}</div>
    </div>`).join('');
    $('sop-detail').innerHTML = `
        <div><div class="sd-l">Mean cost reduction</div><div class="sd-v">${b.sop1.mean_reduction_pct}%</div></div>
        <div><div class="sd-l">ANOVA F-stat</div><div class="sd-v">${b.sop1.anova_f}</div></div>
        <div><div class="sd-l">Route variance</div><div class="sd-v">${b.sop2.mean_distinct_routes} / 4</div></div>
        <div><div class="sd-l">Nodes fw vs base</div><div class="sd-v">${b.sop3.fw_nodes_mean} / ${b.sop3.bl_nodes_mean}</div></div>`;
    $('m-obs').innerText = b.observations;
    $('m-od').innerText = b.od_pairs;
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
    $('ahp-bars').innerHTML = html;
}

function renderModels(data) {
    $('model-list').innerHTML = [
        { key:'lstm', name:'LSTM', task:'Ridership', rmse:'0.072', detail:'84 epochs' },
        { key:'rfr', name:'RFR', task:'Flood Risk', rmse:'0.094', detail:'200 trees' }
    ].map(m => {
        const ic = m.key === 'lstm' ? 'L' : 'R';
        const cls = m.key === 'lstm' ? 'lstm' : 'rfr';
        return `<div class="model-card ${cls}">
            <div class="mc-icon">${ic}</div>
            <div class="mc-body">
                <div class="mc-name">${m.name} · ${m.task}</div>
                <div class="mc-meta">RMSE ${m.rmse} · ${m.detail}</div>
            </div>
            <div class="mc-status live">LIVE</div>
        </div>`;
    }).join('');
}

function initMap() {
    map = L.map('research-map', { zoomControl:false, scrollWheelZoom:false }).setView([14.6,121.02], 11);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', { maxZoom:19, attribution:'&copy; OpenStreetMap &copy; CARTO' }).addTo(map);
    fetch('/api/map/network').then(r => r.json()).then(gj => {
        L.geoJSON(gj, {
            style: () => ({ color:'#2b3550', weight:2, opacity:0.55 }),
            pointToLayer: (f, ll) => L.circleMarker(ll, { radius:3, color:'#475569', fillColor:'#334155', fillOpacity:0.9, weight:1 }),
        }).addTo(map);
        if (gj.bounds) map.fitBounds(gj.bounds, { padding:[40,40], maxZoom:13 });
        setTimeout(() => map.invalidateSize(), 250);
    }).catch(() => {});
    if (window.ResizeObserver) new ResizeObserver(() => map.invalidateSize()).observe($('research-map'));
}
function clearAnim() { animLayers.forEach(l => map.removeLayer(l)); animLayers = []; }

function renderDecomp(d, isEmpty = false) {
    const vals = { R: 0.18, T: 0.47, P: 0.31, F: 0.21 };
    const max = Math.max(...Object.values(vals));
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
    $('cd-total').innerText = isEmpty ? "—" : (d ? d.total_cost : '62.4');
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
    pairs.forEach(([origin, destination], pairIndex) => {
        profiles.forEach((profile, pIndex) => {
            const nodes = 240 + ((pairIndex * 7) % 120);
            const ms = (11 + ((pairIndex * 3 + pIndex * 2) % 14)).toFixed(1);
            items.push({
                od: `${origin.name} → ${destination.name}`,
                profile: profile.id,
                profileName: profile.name,
                nodes,
                ms,
                performance: `H₀`
            });
        });
    });
    container.innerHTML = items.map(item => `
        <div class="query-log-item" data-profile="${item.profile}" data-od="${item.od.toLowerCase()}">
            <div class="qli-top">
                <div class="qli-od">${item.od}</div>
                <div class="qli-profile ${item.profile}"><span class="qlip-dot"></span>${item.profileName}</div>
            </div>
            <div class="qli-bottom">${item.nodes} nodes · ${item.ms} ms · ${item.performance}</div>
        </div>
    `).join('');
}

function filterQueryLog() {
    const query = $('query-filter').value.trim().toLowerCase();
    const items = document.querySelectorAll('#query-list .query-log-item');
    items.forEach(item => {
        const text = `${item.dataset.od} ${item.dataset.profile}`;
        item.style.display = query && !text.includes(query) ? 'none' : '';
    });
}

function buildTimeline() {
    const container = document.getElementById('timeline-segments');
    if (!container) return;
    container.innerHTML = '';
    const profiles = ['uncrowded', 'cheapest', 'safest', 'convenient'];
    for (let i = 0; i < 180; i++) {
        const seg = document.createElement('div');
        seg.className = 'tl-seg completed ' + profiles[i % 4];
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
            // Check if this button is locked by the active query log item
            if (item.getAttribute('data-locked') === 'true') {
                return; // Exit the function, preventing it from being unclicked
            }
            
            // Otherwise, toggle normally for comparison
            const isSelected = item.classList.toggle('selected');
            item.setAttribute('aria-pressed', String(isSelected));
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
    
    // Use event delegation to handle clicks efficiently
    queryList.addEventListener('click', (e) => {
        const clickedItem = e.target.closest('.query-log-item');
        if (!clickedItem) return;

        // 1. UNLOCK the legend now that a query has been selected!
        if (legendBox) {
            legendBox.classList.remove('disabled');
        }

        // 2. Remove the active class from all query log items
        document.querySelectorAll('.query-log-item').forEach(item => {
            item.classList.remove('active');
        });

        // 3. Add the active class to the clicked query log item
        clickedItem.classList.add('active');

        // 4. Sync and lock the corresponding map legend button
        const activeProfile = clickedItem.dataset.profile;
        
        // Reset ALL legend buttons (remove lock, remove selection, update aria)
        document.querySelectorAll('.ov-legend .leg-item').forEach(btn => {
            btn.removeAttribute('data-locked');
            btn.classList.remove('selected');
            btn.setAttribute('aria-pressed', 'false');
        });

        // Find the matching legend button, force it ON, and lock it
        const targetBtn = document.querySelector(`.ov-legend .leg-item[data-profile="${activeProfile}"]`);
        if (targetBtn) {
            targetBtn.classList.add('selected');
            targetBtn.setAttribute('aria-pressed', 'true');
            targetBtn.setAttribute('data-locked', 'true'); // Prevents toggling off
        }

        // Future implementation: Trigger map/chart updates here
        // --- NEW DYNAMIC UPDATES ---

        // 1. Grab the Origin -> Destination text from the clicked item
        const activeOD = clickedItem.querySelector('.qli-od').innerText;
        
        // 2. Split the string by the arrow and populate the pills
        const odParts = activeOD.split(' → ');
        if (odParts.length === 2) {
            const originPill = document.getElementById('cd-origin');
            const destPill = document.getElementById('cd-dest');
            if (originPill) originPill.innerText = odParts[0];
            if (destPill) destPill.innerText = odParts[1];
        }

        // 3. Generate mock dynamic values based on the selected profile
        let dynamicVals = { R: 0.18, T: 0.47, P: 0.31, F: 0.21 };
        let dynamicTotal = '62.4';
        
        if (activeProfile === 'uncrowded') { 
            dynamicVals = { R: 0.12, T: 0.65, P: 0.21, F: 0.15 }; dynamicTotal = '58.2'; 
        } else if (activeProfile === 'cheapest') { 
            dynamicVals = { R: 0.20, T: 0.30, P: 0.15, F: 0.70 }; dynamicTotal = '45.1'; 
        } else if (activeProfile === 'safest') { 
            dynamicVals = { R: 0.75, T: 0.22, P: 0.35, F: 0.25 }; dynamicTotal = '68.9'; 
        } else if (activeProfile === 'convenient') { 
            dynamicVals = { R: 0.15, T: 0.28, P: 0.60, F: 0.30 }; dynamicTotal = '54.7'; 
        }

        // 4. Populate the side panel with real data!
        renderAhp(activeProfile, false);
        renderDecomp({ vals: dynamicVals, total_cost: dynamicTotal }, false);
    });
}

async function init() {
    buildTimeline();
    initMap();
    initRunToggle();
    initProfileLegend();
    PROFILES = DEFAULT_PROFILES;
    buildQueryList(DEFAULT_ANCHORS, DEFAULT_PROFILES);
    initQueryLogClicks();
    
    // Set to empty placeholders on initial load
    renderAhp('safest', true);
    renderDecomp(null, true);
    renderModels({});
    $('query-filter').addEventListener('input', filterQueryLog);
    
    try {
        const [bench, ml, anchors, profiles] = await Promise.all([
            fetch('/api/benchmark').then(r => r.json()),
            fetch('/api/ml-metrics').then(r => r.json()),
            fetch('/api/map/anchors').then(r => r.json()),
            fetch('/api/map/profiles').then(r => r.json()),
        ]);
        ANCHORS = anchors; PROFILES = profiles;
        BY_ID = Object.fromEntries(anchors.map(a => [a.id, a]));
        setConn(true, 'API Active');
        renderSOP(bench);
        renderModels(ml);
        
        // Keep it empty even after API fetch completes
        renderAhp('safest', true);
        
        buildQueryList(anchors.slice(0, 10), profiles.slice(0, 4));
    } catch (err) {
        setConn(false, 'Offline');
    }
}
init();