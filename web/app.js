const output = document.getElementById('output');
const statusBox = document.getElementById('status');

// Views
const tabRouteBtn = document.getElementById('tab-route');
const tabRealtimeBtn = document.getElementById('tab-realtime');
const viewRoute = document.getElementById('view-route');
const viewRealtime = document.getElementById('view-realtime');

const rtLinesBox = document.getElementById('rt-lines');
const btnRtRefresh = document.getElementById('btn-rt-refresh');
const btnRtClear = document.getElementById('btn-rt-clear');

let statusTimer = null;
let statusStartedAt = null;

let realtimeViewActive = false;
let rtRoutesById = new Map(); // route_id -> route meta
let rtSelectedRouteIds = new Set();
let rtLineLayers = new Map(); // route_id -> array of polyline layers
let rtVehicleMarkers = new Map(); // vehicle key -> marker
let rtStopMarkersByRoute = new Map(); // route_id -> array of markers
let rtPollTimer = null;

function setStatus(text) {
  if (!statusBox) return;
  statusBox.textContent = text || '';
}

function startStatusTimer(prefix) {
  stopStatusTimer();
  statusStartedAt = Date.now();
  const tick = () => {
    const s = Math.floor((Date.now() - statusStartedAt) / 1000);
    const extra = s >= 1 ? `\nTiempo: ${s}s` : '';
    setStatus(`${prefix}${extra}`);
  };
  tick();
  statusTimer = setInterval(tick, 1000);
}

function stopStatusTimer(finalText) {
  if (statusTimer) clearInterval(statusTimer);
  statusTimer = null;
  statusStartedAt = null;
  if (finalText !== undefined) setStatus(finalText);
}

function setOutputText(text) {
  if (!output) return;
  output.textContent = String(text || '');
}

function setOutputHtml(html) {
  if (!output) return;
  output.innerHTML = String(html || '');
}

function escapeHtml(s) {
  return String(s || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function num(id) {
  const v = document.getElementById(id).value;
  return v === '' ? null : Number(v);
}

function val(id) {
  return document.getElementById(id).value;
}

function buildRequest() {
  const oLat = num('o-lat');
  const oLon = num('o-lon');
  const dLat = num('d-lat');
  const dLon = num('d-lon');
  if ([oLat, oLon, dLat, dLon].some((x) => x === null || Number.isNaN(x))) {
    throw new Error('Falta origen/destino (lat/lon)');
  }

  const departAtRaw = val('depart-at');
  const preference = val('preference');

  const body = {
    origin: { lat: oLat, lon: oLon },
    destination: { lat: dLat, lon: dLon },
    preference,
  };

  // If provided, convert datetime-local -> ISO
  if (departAtRaw) {
    body.depart_at = new Date(departAtRaw).toISOString();
  }

  return body;
}

async function postJson(path, body) {
  const resp = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(`${resp.status} ${resp.statusText}: ${JSON.stringify(data)}`);
  }
  return data;
}

async function getJson(path) {
  const resp = await fetch(path);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(`${resp.status} ${resp.statusText}: ${JSON.stringify(data)}`);
  }
  return data;
}

// Map
const map = L.map('map').setView([28.123, -15.43], 13);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors',
}).addTo(map);

let originMarker = null;
let destMarker = null;
let legLayers = [];
let stopMarkers = [];

function setMarker(which, latlng) {
  const { lat, lng } = latlng;

  if (which === 'origin') {
    if (originMarker) originMarker.remove();
    originMarker = L.marker([lat, lng]).addTo(map).bindPopup('Origen').openPopup();
    document.getElementById('o-lat').value = lat.toFixed(6);
    document.getElementById('o-lon').value = lng.toFixed(6);
  } else {
    if (destMarker) destMarker.remove();
    destMarker = L.marker([lat, lng]).addTo(map).bindPopup('Destino').openPopup();
    document.getElementById('d-lat').value = lat.toFixed(6);
    document.getElementById('d-lon').value = lng.toFixed(6);
  }

  clearRouteLayers();
}

function clearRouteLayers() {
  for (const layer of legLayers) {
    try { layer.remove(); } catch (_) {}
  }
  legLayers = [];

  for (const m of stopMarkers) {
    try { m.remove(); } catch (_) {}
  }
  stopMarkers = [];
}

function clearRealtimeLayers() {
  for (const layer of rtLineLayers.values()) {
    const layers = Array.isArray(layer) ? layer : [layer];
    for (const l of layers) {
      try { l.remove(); } catch (_) {}
    }
  }
  rtLineLayers = new Map();

  for (const marker of rtVehicleMarkers.values()) {
    try { marker.remove(); } catch (_) {}
  }
  rtVehicleMarkers = new Map();

  for (const markers of rtStopMarkersByRoute.values()) {
    for (const m of markers) {
      try { m.remove(); } catch (_) {}
    }
  }
  rtStopMarkersByRoute = new Map();
}

async function ensureRouteStops(routeId) {
  if (rtStopMarkersByRoute.has(routeId)) return;

  const route = rtRoutesById.get(routeId);
  const color = rtRouteColor(route);

  const stops = await getJson(`/api/realtime/routes/${encodeURIComponent(routeId)}/stops`);
  const markers = [];
  (Array.isArray(stops) ? stops : []).forEach((s) => {
    const loc = s?.location;
    if (!loc || typeof loc.lat !== 'number' || typeof loc.lon !== 'number') return;
    const label = `${escapeHtml(s.name || '')}<br/><span class="muted">#${escapeHtml(s.stop_id || '')}</span>`;
    const marker = L.circleMarker([loc.lat, loc.lon], {
      radius: 4,
      weight: 1,
      color: '#111111',
      fillColor: '#848884',
      fillOpacity: 0.35,
    }).addTo(map);
    marker.bindPopup(label);
    markers.push(marker);
  });

  rtStopMarkersByRoute.set(routeId, markers);
}

function normalizeGtfsColor(raw) {
  if (!raw) return null;
  const c = String(raw).trim().replace(/^#/, '').toUpperCase();
  if (!/^[0-9A-F]{6}$/.test(c)) return null;
  return `#${c}`;
}

function hashToColorHex(input) {
  // Deterministic fallback if GTFS route_color is missing.
  const s = String(input || '');
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h) + s.charCodeAt(i);
    h |= 0;
  }
  const palette = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b'];
  const idx = Math.abs(h) % palette.length;
  return palette[idx];
}

function legLabel(leg) {
  if (!leg || leg.mode !== 'bus') return 'Caminando';
  const line = leg.line || {};
  const name = line.short_name || line.long_name || line.route_id || 'Línea';
  return `Guagua: ${name}`;
}

function fmtCoord(p) {
  if (!p) return '(?)';
  const lat = typeof p.lat === 'number' ? p.lat.toFixed(5) : '?';
  const lon = typeof p.lon === 'number' ? p.lon.toFixed(5) : '?';
  return `${lat}, ${lon}`;
}

function fmtPlace(p, name) {
  const n = typeof name === 'string' ? name.trim() : '';
  if (n) return n;
  return fmtCoord(p);
}

function fmtMeters(m) {
  if (typeof m !== 'number' || Number.isNaN(m)) return '';
  if (m >= 1000) return `${(m / 1000).toFixed(2)} km`;
  return `${Math.round(m)} m`;
}

function fmtSeconds(s) {
  if (typeof s !== 'number' || Number.isNaN(s)) return '';
  const mins = Math.round(s / 60);
  if (mins < 60) return `${mins} min`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${h} h ${m} min`;
}

function parseIsoDate(x) {
  if (!x) return null;
  const d = new Date(x);
  if (Number.isNaN(d.getTime())) return null;
  return d;
}

function pad2(n) {
  return String(n).padStart(2, '0');
}

function fmtHHMM(d) {
  if (!d) return '';
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

function fmtTimeRange(departAt, arriveAt) {
  const d0 = parseIsoDate(departAt);
  const d1 = parseIsoDate(arriveAt);
  if (d0 && d1) return `${fmtHHMM(d0)} → ${fmtHHMM(d1)}`;
  if (d0) return `Salida ${fmtHHMM(d0)}`;
  if (d1) return `Llega ${fmtHHMM(d1)}`;
  return '';
}

function diffMinutes(a, b) {
  const d0 = parseIsoDate(a);
  const d1 = parseIsoDate(b);
  if (!d0 || !d1) return null;
  const ms = d1.getTime() - d0.getTime();
  return Math.round(ms / 60000);
}

function routeToSteps(route) {
  if (!route || !Array.isArray(route.legs) || route.legs.length === 0) {
    return 'No hay ruta.';
  }

  const lines = [];
  lines.push('Itinerario');
  lines.push('');

  for (let i = 0; i < route.legs.length; i++) {
    const leg = route.legs[i];
    const dist = fmtMeters(leg.distance_m);
    const dur = fmtSeconds(leg.duration_s);
    const extra = [dist, dur].filter(Boolean).join(' · ');

    if (leg.mode === 'walk') {
      lines.push(`${i + 1}. Camina desde (${fmtCoord(leg.origin)}) hasta (${fmtCoord(leg.destination)})${extra ? ` [${extra}]` : ''}`);
    } else {
      const line = leg.line || {};
      const name = line.short_name || line.long_name || line.route_id || 'Línea';
      lines.push(`${i + 1}. En la parada, coge la guagua ${name} desde (${fmtCoord(leg.origin)}) hasta (${fmtCoord(leg.destination)})${extra ? ` [${extra}]` : ''}`);
    }
  }

  lines.push('');
  if (typeof route.total_distance_m === 'number') {
    lines.push(`Distancia total: ${fmtMeters(route.total_distance_m)}`);
  }
  if (typeof route.total_duration_s === 'number') {
    lines.push(`Duración total: ${fmtSeconds(route.total_duration_s)}`);
  }

  return lines.join('\n');
}

function renderItinerary(route) {
  if (!route || !Array.isArray(route.legs) || route.legs.length === 0) {
    return `<div class="itinerary-title">Itinerario</div><div class="muted">No hay ruta.</div>`;
  }

  const items = [];
  for (let i = 0; i < route.legs.length; i++) {
    const leg = route.legs[i];
    items.push({ kind: 'leg', leg, i });

    const next = route.legs[i + 1];
    if (leg && leg.mode === 'bus' && next && next.mode === 'bus') {
      items.push({ kind: 'transfer', from: leg, to: next });
    }
  }

  const stepsHtml = items.map((item, idx) => {
    if (item.kind === 'transfer') {
      const place = fmtPlace(item.from.destination, item.from.destination_name);
      const stopId = item.from.destination_stop_id ? ` <span class="muted-inline">(#${escapeHtml(item.from.destination_stop_id)})</span>` : '';
      const waitMin = diffMinutes(item.from.arrive_at, item.to.depart_at);
      const timeRange = fmtTimeRange(item.from.arrive_at, item.to.depart_at);
      const chips = [
        (waitMin !== null && waitMin > 0) ? `Espera ${waitMin} min` : '',
        timeRange,
      ].filter(Boolean).map((x) => `<span class="chip">${escapeHtml(x)}</span>`).join('');

      return `
        <div class="step">
          <div class="step-icon">⇄</div>
          <div class="step-main">
            <div class="step-head">
              <div class="step-title">Transbordo</div>
              <div class="chips">${chips}</div>
            </div>
            <div class="step-sub">En <b>${escapeHtml(place)}</b>${stopId}</div>
          </div>
        </div>
      `;
    }

    const leg = item.leg;
    const dist = fmtMeters(leg.distance_m);
    const dur = fmtSeconds(leg.duration_s);
    const timeRange = fmtTimeRange(leg.depart_at, leg.arrive_at);
    const chips = [dist, dur, timeRange].filter(Boolean).map((x) => `<span class="chip">${escapeHtml(x)}</span>`).join('');

    if (leg.mode === 'walk') {
      const from = fmtPlace(leg.origin, leg.origin_name);
      const to = fmtPlace(leg.destination, leg.destination_name);
      const toStop = leg.destination_stop_id ? ` <span class="muted-inline">(#${escapeHtml(leg.destination_stop_id)})</span>` : '';

      return `
        <div class="step">
          <div class="step-icon">W</div>
          <div class="step-main">
            <div class="step-head">
              <div class="step-title">Caminar</div>
              <div class="chips">${chips}</div>
            </div>
            <div class="step-sub">Desde <b>${escapeHtml(from)}</b> hasta <b>${escapeHtml(to)}</b>${toStop}</div>
          </div>
        </div>
      `;
    }

    const line = leg.line || {};
    const name = line.short_name || line.long_name || line.route_id || 'Línea';
    const color = normalizeGtfsColor(line.color) || hashToColorHex(line.route_id || leg.trip_id || name);
    const from = fmtPlace(leg.origin, leg.origin_name);
    const to = fmtPlace(leg.destination, leg.destination_name);
    const fromStop = leg.origin_stop_id ? ` <span class="muted-inline">(#${escapeHtml(leg.origin_stop_id)})</span>` : '';
    const toStop = leg.destination_stop_id ? ` <span class="muted-inline">(#${escapeHtml(leg.destination_stop_id)})</span>` : '';

    const prevLeg = item.i > 0 ? route.legs[item.i - 1] : null;
    const waitMin = prevLeg && prevLeg.arrive_at ? diffMinutes(prevLeg.arrive_at, leg.depart_at) : null;
    const waitNote = (waitMin !== null && waitMin > 0)
      ? ` <span class="muted-inline">(Espera ${escapeHtml(waitMin)} min)</span>`
      : '';

    return `
      <div class="step">
        <div class="step-icon bus">B</div>
        <div class="step-main">
          <div class="step-head">
            <div class="step-title">
              <span class="line-badge">
                <span class="line-dot" style="background:${escapeHtml(color)}"></span>
                Guagua ${escapeHtml(name)}
              </span>
            </div>
            <div class="chips">${chips}</div>
          </div>
          <div class="step-sub">Desde <b>${escapeHtml(from)}</b>${fromStop} hasta <b>${escapeHtml(to)}</b>${toStop}</div>
          ${waitNote ? `<div class="step-sub">${waitNote}</div>` : ''}
        </div>
      </div>
    `;
  }).join('');

  const totalDist = typeof route.total_distance_m === 'number' ? fmtMeters(route.total_distance_m) : '';
  const totalDur = typeof route.total_duration_s === 'number' ? fmtSeconds(route.total_duration_s) : '';

  const summaryLeft = totalDist ? `Distancia total: <b>${escapeHtml(totalDist)}</b>` : '';
  const summaryRight = totalDur ? `Duración total: <b>${escapeHtml(totalDur)}</b>` : '';

  return `
    <div class="itinerary-title">Itinerario</div>
    <div class="steps">${stepsHtml}</div>
    <div class="itinerary-summary">
      <div>${summaryLeft}</div>
      <div>${summaryRight}</div>
    </div>
  `;
}

function addStopMarker(lat, lon, opts) {
  const marker = L.circleMarker([lat, lon], {
    radius: 6,
    weight: 2,
    color: opts?.strokeColor || '#111111',
    fillColor: opts?.fillColor || '#ffffff',
    fillOpacity: 1.0,
  }).addTo(map);
  if (opts?.label) marker.bindPopup(opts.label);
  stopMarkers.push(marker);
}

function drawRoute(route) {
  clearRouteLayers();
  if (!route || !Array.isArray(route.legs)) return;

  const allLatLngs = [];

  const seenPoints = new Set();
  function markPoint(p, kind, color, label) {
    if (!p || typeof p.lat !== 'number' || typeof p.lon !== 'number') return;
    const key = `${p.lat.toFixed(6)},${p.lon.toFixed(6)}:${kind}`;
    if (seenPoints.has(key)) return;
    seenPoints.add(key);
    addStopMarker(p.lat, p.lon, { strokeColor: '#111111', fillColor: color, label });
  }

  for (let i = 0; i < route.legs.length; i++) {
    const leg = route.legs[i];
    const pts = Array.isArray(leg.path) && leg.path.length >= 2
      ? leg.path
      : [leg.origin, leg.destination];

    const latlngs = pts
      .filter((p) => p && typeof p.lat === 'number' && typeof p.lon === 'number')
      .map((p) => [p.lat, p.lon]);

    if (latlngs.length < 2) continue;

    const busColor = normalizeGtfsColor(leg?.line?.color);
    const busFallback = hashToColorHex(leg?.line?.route_id || leg?.trip_id || legLabel(leg));
    const color = leg.mode === 'bus' ? (busColor || busFallback) : '#666666';

    const layer = L.polyline(latlngs, { weight: 5, color, opacity: 0.9 }).addTo(map);
    layer.bindPopup(legLabel(leg));
    legLayers.push(layer);
    allLatLngs.push(...latlngs);

    // Mark boarding/alighting/transfers.
    const prev = route.legs[i - 1];
    const next = route.legs[i + 1];

    if (leg.mode === 'bus') {
      const lineName = leg?.line?.short_name || leg?.line?.long_name || leg?.line?.route_id || 'Línea';
      const boardLabel = `Sube a: ${lineName}`;
      const alightLabel = next && next.mode === 'bus' ? `Transbordo (baja de: ${lineName})` : `Baja de: ${lineName}`;

      // Boarding point (walk->bus or start of bus sequence)
      if (!prev || prev.mode !== 'bus') {
        markPoint(leg.origin, 'board', color, boardLabel);
      }

      // Alighting point (bus->walk or bus->bus transfer)
      markPoint(leg.destination, next && next.mode === 'bus' ? 'transfer' : 'alight', color, alightLabel);
    }
  }

  if (allLatLngs.length >= 2) {
    map.fitBounds(allLatLngs, { padding: [20, 20] });
  }
}

map.on('click', (e) => {
  if (realtimeViewActive) return;
  if (!originMarker) return setMarker('origin', e.latlng);
  if (!destMarker) return setMarker('dest', e.latlng);
  // If both are set, overwrite destination.
  return setMarker('dest', e.latlng);
});

function setActiveView(which) {
  const isRealtime = which === 'realtime';
  realtimeViewActive = isRealtime;

  if (viewRoute) viewRoute.classList.toggle('hidden', isRealtime);
  if (viewRealtime) viewRealtime.classList.toggle('hidden', !isRealtime);

  if (tabRouteBtn) {
    tabRouteBtn.classList.toggle('tab-active', !isRealtime);
    tabRouteBtn.setAttribute('aria-selected', String(!isRealtime));
  }
  if (tabRealtimeBtn) {
    tabRealtimeBtn.classList.toggle('tab-active', isRealtime);
    tabRealtimeBtn.setAttribute('aria-selected', String(isRealtime));
  }

  if (isRealtime) {
    clearRouteLayers();
    setOutputText('');
    startRealtimeView();
  } else {
    stopRealtimeView();
    clearRealtimeLayers();
    setStatus('');
  }
}

function routeDisplayName(r) {
  if (!r) return '';
  return r.short_name || r.long_name || r.route_id || '';
}

function routeDisplayDetail(r) {
  if (!r) return '';
  const parts = [];
  if (r.long_name && r.short_name && r.long_name !== r.short_name) parts.push(r.long_name);
  return parts.join(' · ');
}

function rtRouteColor(r) {
  return normalizeGtfsColor(r?.color) || hashToColorHex(r?.route_id || routeDisplayName(r));
}

function renderRealtimeRoutes(routes) {
  if (!rtLinesBox) return;
  if (!Array.isArray(routes) || routes.length === 0) {
    rtLinesBox.innerHTML = '<div class="muted">No hay líneas.</div>';
    return;
  }

  rtRoutesById = new Map();
  for (const r of routes) {
    if (r && r.route_id) rtRoutesById.set(r.route_id, r);
  }

  const html = routes.map((r) => {
    const id = escapeHtml(r.route_id);
    const name = escapeHtml(routeDisplayName(r) || r.route_id);
    const detail = escapeHtml(routeDisplayDetail(r));
    const color = escapeHtml(rtRouteColor(r));
    const checked = rtSelectedRouteIds.has(r.route_id) ? 'checked' : '';
    return `
      <label class="rt-line">
        <input type="checkbox" data-route-id="${id}" ${checked} />
        <span class="rt-line-label">
          <span class="line-dot" style="background:${color}"></span>
          <span><b>${name}</b>${detail ? ` <span class="muted">${detail}</span>` : ''}</span>
        </span>
      </label>
    `;
  }).join('');

  rtLinesBox.innerHTML = html;

  for (const el of rtLinesBox.querySelectorAll('input[type=checkbox][data-route-id]')) {
    el.addEventListener('change', async (ev) => {
      const rid = ev.target?.getAttribute('data-route-id');
      if (!rid) return;
      if (ev.target.checked) rtSelectedRouteIds.add(rid);
      else rtSelectedRouteIds.delete(rid);

      await syncRealtimeLayers();
      await refreshRealtimeVehicles();
    });
  }
}

async function loadRealtimeRoutes() {
  try {
    startStatusTimer('Cargando líneas (tiempo real)...');
    const routes = await getJson('/api/realtime/routes');
    renderRealtimeRoutes(routes);
    stopStatusTimer('Líneas cargadas.');
  } catch (e) {
    stopStatusTimer('Error cargando líneas.');
    if (rtLinesBox) rtLinesBox.innerHTML = `<div class="muted">${escapeHtml(String(e))}</div>`;
  }
}

async function ensureRouteShape(routeId) {
  if (rtLineLayers.has(routeId)) return;

  const route = rtRoutesById.get(routeId);
  const color = rtRouteColor(route);

  const data = await getJson(`/api/realtime/routes/${encodeURIComponent(routeId)}/shape`);

  // New API: { route_id, shapes: [{shape_id, points:[...]}] }
  // Backward compatible: { route_id, points:[...] }
  const shapes = Array.isArray(data?.shapes) ? data.shapes : null;

  const layers = [];
  if (shapes && shapes.length) {
    for (const sh of shapes) {
      const pts = Array.isArray(sh?.points) ? sh.points : [];
      const latlngs = pts
        .filter((p) => p && typeof p.lat === 'number' && typeof p.lon === 'number')
        .map((p) => [p.lat, p.lon]);
      if (latlngs.length < 2) continue;
      const layer = L.polyline(latlngs, { weight: 5, color, opacity: 0.7 }).addTo(map);
      layers.push(layer);
    }
  } else {
    const pts = Array.isArray(data?.points) ? data.points : [];
    const latlngs = pts
      .filter((p) => p && typeof p.lat === 'number' && typeof p.lon === 'number')
      .map((p) => [p.lat, p.lon]);
    if (latlngs.length >= 2) {
      layers.push(L.polyline(latlngs, { weight: 5, color, opacity: 0.7 }).addTo(map));
    }
  }

  if (!layers.length) return;
  for (const layer of layers) {
    layer.bindPopup(`Línea ${escapeHtml(routeDisplayName(route) || routeId)}`);
  }
  rtLineLayers.set(routeId, layers);
}

async function syncRealtimeLayers() {
  // Add missing shapes
  for (const rid of rtSelectedRouteIds) {
    try {
      await ensureRouteShape(rid);
      await ensureRouteStops(rid);
    } catch (_) {
      // ignore per-route errors
    }
  }

  // Remove unselected shapes
  for (const [rid, layers] of rtLineLayers.entries()) {
    if (!rtSelectedRouteIds.has(rid)) {
      const ls = Array.isArray(layers) ? layers : [layers];
      for (const l of ls) {
        try { l.remove(); } catch (_) {}
      }
      rtLineLayers.delete(rid);
    }
  }

  for (const [rid, markers] of rtStopMarkersByRoute.entries()) {
    if (!rtSelectedRouteIds.has(rid)) {
      for (const m of markers) {
        try { m.remove(); } catch (_) {}
      }
      rtStopMarkersByRoute.delete(rid);
    }
  }

  // Remove vehicle markers for deselected routes even if refresh fails.
  for (const [key, marker] of rtVehicleMarkers.entries()) {
    const mrid = marker?._rtRouteId;
    if (mrid && !rtSelectedRouteIds.has(mrid)) {
      try { marker.remove(); } catch (_) {}
      rtVehicleMarkers.delete(key);
    }
  }
}

function vehicleKey(v, idx) {
  return v.vehicle_id || v.trip_id || `${v.route_id || 'unknown'}:${idx}`;
}

async function refreshRealtimeVehicles() {
  if (!realtimeViewActive) return;

  if (!rtSelectedRouteIds || rtSelectedRouteIds.size === 0) {
    setStatus('Selecciona al menos una línea.');
    // Clear vehicles if nothing selected.
    for (const marker of rtVehicleMarkers.values()) {
      try { marker.remove(); } catch (_) {}
    }
    rtVehicleMarkers = new Map();
    return;
  }

  try {
    const qs = new URLSearchParams();
    for (const rid of rtSelectedRouteIds) qs.append('route_id', rid);
    const data = await getJson(`/api/realtime/vehicles?${qs.toString()}`);
    const rawVehicles = Array.isArray(data?.vehicles) ? data.vehicles : [];
    const vehicles = rawVehicles.filter((v) => v && v.route_id && rtSelectedRouteIds.has(String(v.route_id)));

    const seen = new Set();
    vehicles.forEach((v, idx) => {
      if (!v || typeof v.lat !== 'number' || typeof v.lon !== 'number') return;
      const key = vehicleKey(v, idx);
      seen.add(key);

      const r = v.route_id ? rtRoutesById.get(v.route_id) : null;
      const color = rtRouteColor(r || { route_id: v.route_id || key });

      const label = `Vehículo ${escapeHtml(v.vehicle_id || '?')}<br/>Línea ${escapeHtml(routeDisplayName(r) || v.route_id || '?')}`;

      const existing = rtVehicleMarkers.get(key);
      if (existing) {
        existing.setLatLng([v.lat, v.lon]);
      } else {
        const marker = L.circleMarker([v.lat, v.lon], {
          radius: 7,
          weight: 2,
          color: '#111111',
          fillColor: color,
          fillOpacity: 1.0,
        }).addTo(map);
        marker._rtRouteId = String(v.route_id || '');
        marker.bindPopup(label);
        rtVehicleMarkers.set(key, marker);
      }
    });

    // Remove stale markers
    for (const [key, marker] of rtVehicleMarkers.entries()) {
      if (!seen.has(key)) {
        try { marker.remove(); } catch (_) {}
        rtVehicleMarkers.delete(key);
      }
    }

    setStatus(`Tiempo real: ${vehicles.length} guaguas.`);
  } catch (e) {
    setStatus(`Tiempo real: error obteniendo guaguas.\n${String(e)}`);
  }
}

function startRealtimeView() {
  stopRealtimeView();
  if (!rtRoutesById || rtRoutesById.size === 0) {
    loadRealtimeRoutes().then(async () => {
      await syncRealtimeLayers();
      await refreshRealtimeVehicles();
    });
  }
  refreshRealtimeVehicles();
  rtPollTimer = setInterval(refreshRealtimeVehicles, 30000);
}

function stopRealtimeView() {
  if (rtPollTimer) clearInterval(rtPollTimer);
  rtPollTimer = null;
}

function clearAll() {
  try { stopStatusTimer(''); } catch (_) {}
  stopRealtimeView();
  clearRealtimeLayers();
  clearRouteLayers();

  if (originMarker) { try { originMarker.remove(); } catch (_) {} }
  if (destMarker) { try { destMarker.remove(); } catch (_) {} }
  originMarker = null;
  destMarker = null;

  document.getElementById('o-lat').value = '';
  document.getElementById('o-lon').value = '';
  document.getElementById('d-lat').value = '';
  document.getElementById('d-lon').value = '';
  document.getElementById('request-id').value = '';

  setStatus('');
  setOutputText('');
}

// Buttons

document.getElementById('btn-sync').addEventListener('click', async () => {
  try {
    setOutputText('');
    startStatusTimer('Calculando ruta (sync).\nNota: la primera vez puede tardar porque se descarga/construye el grafo OSM.');
    const body = buildRequest();
    const data = await postJson('/api/routes', body);
    drawRoute(data);
    setOutputHtml(renderItinerary(data));
    stopStatusTimer('Ruta calculada (sync).');
  } catch (e) {
    stopStatusTimer('Error calculando (sync).');
    setOutputText(String(e));
  }
});

document.getElementById('btn-async').addEventListener('click', async () => {
  try {
    setOutputText('');
    startStatusTimer('Encolando ruta (async)...');
    const body = buildRequest();
    const data = await postJson('/api/routes/async', body);
    document.getElementById('request-id').value = data.request_id || '';
    setOutputText(`Job encolado. request_id=${data.request_id || ''}`);
    stopStatusTimer(`Job encolado. request_id=${data.request_id}`);

    // Auto-poll until completion to avoid user waiting blind.
    if (data.request_id) {
      startStatusTimer('Calculando ruta (async). Consultando estado...');
      for (let i = 0; i < 600; i++) { // up to ~10min
        const job = await getJson(`/api/routes/jobs/${encodeURIComponent(data.request_id)}`);
        if (job.status === 'SUCCESS' && job.result) {
          drawRoute(job.result);
          setOutputHtml(renderItinerary(job.result));
          stopStatusTimer('Ruta calculada (async).');
          return;
        }
        if (job.status === 'ERROR') {
          setOutputText(`Error: ${job.error || 'unknown'}`);
          stopStatusTimer('Error calculando (async).');
          return;
        }
        await new Promise((r) => setTimeout(r, 1000));
      }
      stopStatusTimer('Sigue calculando (async). Puedes usar “Consultar” más tarde con el request_id.');
    }
  } catch (e) {
    stopStatusTimer('Error en async.');
    setOutputText(String(e));
  }
});

document.getElementById('btn-poll').addEventListener('click', async () => {
  try {
    const rid = val('request-id').trim();
    if (!rid) throw new Error('Falta request_id');
    setOutputText('');
    startStatusTimer('Consultando estado del job...');
    const data = await getJson(`/api/routes/jobs/${encodeURIComponent(rid)}`);

    if (data && data.status === 'SUCCESS' && data.result) {
      drawRoute(data.result);
      setOutputHtml(renderItinerary(data.result));
    } else if (data && data.status === 'ERROR') {
      setOutputText(`Error: ${data.error || 'unknown'}`);
    } else {
      setOutputText(`Estado: ${data.status || 'UNKNOWN'}`);
    }
    stopStatusTimer(`Estado: ${data.status || 'UNKNOWN'}`);
  } catch (e) {
    stopStatusTimer('Error consultando job.');
    setOutputText(String(e));
  }
});

document.getElementById('btn-clear').addEventListener('click', () => {
  clearAll();
});

// Tabs + realtime controls
if (tabRouteBtn) tabRouteBtn.addEventListener('click', () => setActiveView('route'));
if (tabRealtimeBtn) tabRealtimeBtn.addEventListener('click', () => setActiveView('realtime'));

if (btnRtRefresh) btnRtRefresh.addEventListener('click', async () => {
  await syncRealtimeLayers();
  await refreshRealtimeVehicles();
});

if (btnRtClear) btnRtClear.addEventListener('click', () => {
  rtSelectedRouteIds = new Set();
  clearRealtimeLayers();
  if (rtLinesBox) {
    for (const el of rtLinesBox.querySelectorAll('input[type=checkbox][data-route-id]')) {
      el.checked = false;
    }
  }
  setStatus('Capas de tiempo real eliminadas.');
});
