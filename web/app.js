const output = document.getElementById('output');
const statusBox = document.getElementById('status');

let statusTimer = null;
let statusStartedAt = null;

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
  if (!originMarker) return setMarker('origin', e.latlng);
  if (!destMarker) return setMarker('dest', e.latlng);
  // If both are set, overwrite destination.
  return setMarker('dest', e.latlng);
});

function clearAll() {
  try { stopStatusTimer(''); } catch (_) {}
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
