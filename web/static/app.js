"use strict";

/* ---------- icons (Lucide-style line icons) ---------- */
const ICONS = {
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  locate: '<line x1="2" x2="5" y1="12" y2="12"/><line x1="19" x2="22" y1="12" y2="12"/><line x1="12" x2="12" y1="2" y2="5"/><line x1="12" x2="12" y1="19" y2="22"/><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="3"/>',
  swap: '<path d="m21 16-4 4-4-4"/><path d="M17 20V4"/><path d="m3 8 4-4 4 4"/><path d="M7 4v16"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  chevron: '<path d="m6 9 6 6 6-6"/>',
  wheelchair: '<circle cx="16" cy="4" r="1"/><path d="m18 19 1-7-6 1"/><path d="m5 8 3-3 5.5 3-2.36 3.5"/><path d="M4.24 14.5a5 5 0 0 0 6.88 6"/><path d="M13.76 17.5a5 5 0 0 0-6.88-6"/>',
  transfer: '<path d="M8 3 4 7l4 4"/><path d="M4 7h16"/><path d="m16 21 4-4-4-4"/><path d="M20 17H4"/>',
  filter: '<path d="M21 4H14"/><path d="M10 4H3"/><path d="M21 12h-9"/><path d="M8 12H3"/><path d="M21 20h-5"/><path d="M12 20H3"/><path d="M14 2v4"/><path d="M8 10v4"/><path d="M16 18v4"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  sparkle: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 17l.7 1.8 1.8.7-1.8.7L19 22l-.7-1.8-1.8-.7 1.8-.7z"/>',
  bus: '<path d="M8 6v6"/><path d="M15 6v6"/><path d="M2 12h19.6"/><path d="M18 18h3s.5-1.7.8-2.8c.1-.4.2-.8.2-1.2 0-.4-.1-.8-.2-1.2l-1.4-5C20.1 6.8 19.1 6 18 6H4a2 2 0 0 0-2 2v10h3"/><circle cx="7" cy="18" r="2"/><path d="M9 18h5"/><circle cx="16" cy="18" r="2"/>',
  train: '<path d="M8 3.1V7a4 4 0 0 0 8 0V3.1"/><path d="m9 15-1-1"/><path d="m15 15 1-1"/><path d="M9 19c-2.8 0-5-2.2-5-5v-4a8 8 0 0 1 16 0v4c0 2.8-2.2 5-5 5Z"/><path d="m8 19-2 3"/><path d="m16 19 2 3"/>',
  tram: '<rect x="4" y="5" width="16" height="13" rx="3"/><path d="M4 12h16"/><path d="M9 2h6"/><path d="M12 2v3"/><path d="m8 18-2 3"/><path d="m16 18 2 3"/>',
  ship: '<path d="M2 21c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1 .6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/><path d="M19.4 17 21 12l-9-4-9 4 1.6 5"/><path d="M12 2v6"/><path d="M8 5h8"/>',
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
  live: '<circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49"/><path d="M7.76 16.24a6 6 0 0 1 0-8.49"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M4.93 19.07a10 10 0 0 1 0-14.14"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  flag: '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><path d="M4 22v-7"/>',
  pin: '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
  bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
  zap: '<path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
};
const svg = (name) => `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${ICONS[name] || ""}</svg>`;
const icon = (name) => `<span data-icon="${name}" aria-hidden="true">${svg(name)}</span>`;
function hydrateIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((el) => {
    if (el.querySelector("svg")) return;
    if (el.tagName === "BUTTON") {              // buttons keep their label; the icon goes inside
      el.insertAdjacentHTML("afterbegin", icon(el.dataset.icon));
      el.removeAttribute("data-icon");
    } else {
      el.innerHTML = svg(el.dataset.icon);
      el.setAttribute("aria-hidden", "true");
    }
  });
}

/* ---------- helpers ---------- */
const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const TIME = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/New_York" });
const clock = (iso) => (iso ? TIME.format(new Date(iso)) : "");
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
const MODE_ICON = { ROLL: "wheelchair", BUS: "bus", SUBWAY: "train", TRAM: "tram", RAIL: "train", FERRY: "ship" };
const ROLE = { board: "where you board", exit: "where you get off", transfer: "where you change", "no service": "no service", detour: "detour", roll: "rolling" };

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}
function inkFor(hex) {
  const h = (hex || "#9ca3af").replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.55 ? "#111" : "#fff";
}
const colorOf = (leg) => leg.color || "#9ca3af";
function shortName(l) {
  const n = l.route_name || "";
  if (l.mode === "BUS") {
    if (n.startsWith("Silver Line ")) return n.slice(12);
    if (n.startsWith("Bus ")) return n.slice(4);
    return n;
  }
  if (l.mode === "RAIL") return "CR " + n.replace(" Line (Commuter Rail)", "").replace(" (Commuter Rail)", "");
  return n.replace(" Line", "");
}
function linePill(l) {
  const c = colorOf(l);
  return `<span class="line-pill" style="background:${c};color:${inkFor(c)}">${icon(MODE_ICON[l.mode] || "bus")}${esc(shortName(l))}</span>`;
}
function badge(trip, size = "") {
  const first = trip.legs.find((l) => l.transit);
  const mode = first ? MODE_ICON[first.mode] : "wheelchair";
  return `<span class="badge ${size}" style="--c:${first ? colorOf(first) : "#6ee7b7"}">${icon(mode)}<span class="ring"></span></span>`;
}
function mdLite(text) {
  return esc(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}
function withOffset(local) {       // "2026-11-14T09:00" -> "2026-11-14T09:00:00-05:00"
  const d = new Date(local);
  const off = -d.getTimezoneOffset();
  const pad = (n) => String(Math.floor(Math.abs(n))).padStart(2, "0");
  return `${local}:00${off >= 0 ? "+" : "-"}${pad(off / 60)}:${pad(off % 60)}`;
}

/* ---------- state ---------- */
const S = { origin: null, destination: null, here: null, avoid: [], fewer: false, stations: [],
  result: null, sel: 0, watch: null, timer: null, explainSeq: 0, explainHTML: null };

/* ---------- map ---------- */
const EMPTY = { type: "FeatureCollection", features: [] };
let map, mapReady = false, pendingDraw = null, markers = [];

function initMap() {
  map = new maplibregl.Map({
    container: "map",
    style: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    center: [-71.0589, 42.3601], zoom: 11.6, attributionControl: false,
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
  map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-left");
  map.on("load", () => {
    map.addSource("trip", { type: "geojson", data: EMPTY });
    const round = { "line-cap": "round", "line-join": "round" };
    const transit = ["==", ["get", "transit"], true];
    map.addLayer({ id: "glow", type: "line", source: "trip", filter: transit, layout: round,
      paint: { "line-color": ["get", "color"], "line-width": 18, "line-blur": 12, "line-opacity": 0.5 } });
    map.addLayer({ id: "casing", type: "line", source: "trip", filter: transit, layout: round,
      paint: { "line-color": "#0b0c0f", "line-width": 9 } });
    map.addLayer({ id: "core", type: "line", source: "trip", filter: transit, layout: round,
      paint: { "line-color": ["get", "color"], "line-width": 5 } });
    map.addLayer({ id: "roll", type: "line", source: "trip", filter: ["!", transit], layout: round,
      paint: { "line-color": "#e5e7eb", "line-width": 3.5, "line-dasharray": [0.1, 2] } });
    mapReady = true;
    if (pendingDraw) drawTrip(...pendingDraw);
  });
}

function marker(html, lngLat, anchor = "center") {
  const el = document.createElement("div");
  el.innerHTML = html;
  const m = new maplibregl.Marker({ element: el.firstElementChild, anchor }).setLngLat(lngLat).addTo(map);
  markers.push(m);
}

function drawTrip(trip, origin, dest) {
  if (!mapReady) { pendingDraw = [trip, origin, dest]; return; }
  markers.forEach((m) => m.remove());
  markers = [];
  const features = trip.legs.filter((l) => l.geometry && l.geometry.length > 1).map((l) => ({
    type: "Feature",
    properties: { transit: l.transit, color: colorOf(l) },
    geometry: { type: "LineString", coordinates: l.geometry.map(([la, lo]) => [lo, la]) },
  }));
  map.getSource("trip").setData({ type: "FeatureCollection", features });
  trip.legs.forEach((l, i) => {
    if (!l.transit) return;
    const c = colorOf(l);
    marker(`<div class="mk" style="--c:${c}"><div class="mk-badge">${icon(MODE_ICON[l.mode] || "bus")}</div>
      <div class="mk-pill">${l.realtime ? icon("live") : ""}${esc(shortName(l))} · ${esc(clock(l.start))}</div></div>`,
      [l.from.lon, l.from.lat], "top");
    const next = trip.legs.slice(i + 1).find((x) => x.transit);
    if (!next) marker(`<div class="mk-stop" style="--c:${c}"></div>`, [l.to.lon, l.to.lat]);
  });
  if (origin) marker(`<div class="mk-origin" title="Start"></div>`, [origin.lon, origin.lat]);
  if (dest) marker(`<div class="mk-dest" title="Destination">${icon("flag")}</div>`, [dest.lon, dest.lat], "bottom");
  const pts = features.flatMap((f) => f.geometry.coordinates);
  if (origin) pts.push([origin.lon, origin.lat]);
  if (dest) pts.push([dest.lon, dest.lat]);
  if (pts.length) {
    const b = pts.reduce((bb, p) => bb.extend(p), new maplibregl.LngLatBounds(pts[0], pts[0]));
    const wide = window.innerWidth > 900;
    map.fitBounds(b, { padding: { top: 70, bottom: 70, left: 60, right: wide && !$("#detail").hidden ? 450 : 60 },
      maxZoom: 15.5, duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 900 });
  }
  $("#mapEmpty").hidden = true;
}

/* ---------- place fields ---------- */
function setupField(key) {
  const input = $(`#${key}`), list = $(`#${key}List`);
  let items = [], active = -1, timer = null, seq = 0;
  const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); active = -1; };
  const render = () => {
    if (!items.length) return close();
    list.innerHTML = items.map((it, i) => `<li role="option" id="${key}-opt-${i}" aria-selected="${i === active}" data-i="${i}">
      <span class="s-icon">${icon(it.kind === "station" ? "train" : it.kind === "search" ? "search" : "pin")}</span>
      <span><div class="s-name">${esc(it.name)}</div><div class="s-sub">${esc(it.sub || "")}</div></span></li>`).join("");
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    if (active >= 0) input.setAttribute("aria-activedescendant", `${key}-opt-${active}`);
    else input.removeAttribute("aria-activedescendant");
  };
  const lookup = async (address) => {
    const q = input.value.trim();
    if (q.length < 2 || q === "Your location") return close();
    const my = ++seq;
    try {
      items = await api(`/api/places?q=${encodeURIComponent(q)}&address=${address}`);
    } catch { items = []; }
    if (my !== seq) return;
    if (!address && q.length >= 3) items.push({ kind: "search", name: `Search addresses for “${q}”`, sub: "OpenStreetMap" });
    if (address && !items.length) items = [{ kind: "none", name: "No places found in the Boston area", sub: "Try adding a street or town" }];
    active = -1;
    render();
  };
  const pick = (i) => {
    const it = items[i];
    if (!it || it.kind === "none") return;
    if (it.kind === "search") return lookup(true);
    S[key] = { name: it.name, lat: it.lat, lon: it.lon };
    input.value = it.name;
    close();
  };
  input.addEventListener("input", () => {
    S[key] = null;
    clearTimeout(timer);
    timer = setTimeout(() => lookup(false), 160);
  });
  input.addEventListener("keydown", (e) => {
    if (list.hidden) return;
    if (e.key === "ArrowDown") { e.preventDefault(); active = Math.min(active + 1, items.length - 1); render(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); active = Math.max(active - 1, 0); render(); }
    else if (e.key === "Enter" && active >= 0) { e.preventDefault(); pick(active); }
    else if (e.key === "Escape") close();
  });
  input.addEventListener("blur", () => setTimeout(close, 180));
  list.addEventListener("mousedown", (e) => {
    const li = e.target.closest("li");
    if (li) { e.preventDefault(); pick(+li.dataset.i); }
  });
}

function locate() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error("Location isn't available in this browser."));
    const btn = $("#locateBtn");
    btn.classList.add("active");
    navigator.geolocation.getCurrentPosition((p) => {
      S.here = [p.coords.latitude, p.coords.longitude];
      S.origin = { name: "Your location", lat: S.here[0], lon: S.here[1] };
      $("#origin").value = "Your location";
      resolve();
    }, (err) => {
      btn.classList.remove("active");
      reject(new Error(err.code === 1 ? "Location permission was denied. Type a starting point instead."
        : "Couldn't get your location. Type a starting point instead."));
    }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 });
  });
}

/* ---------- options ---------- */
function renderAvoid() {
  $("#avoidTags").innerHTML = S.avoid.map((n, i) => `<span class="tag">${esc(n)}
    <button type="button" data-i="${i}" aria-label="Stop avoiding ${esc(n)}">${icon("x")}</button></span>`).join("");
  const c = $("#avoidCount");
  c.hidden = !S.avoid.length;
  c.textContent = S.avoid.length;
}
function addAvoid(text) {
  const name = S.stations.find((s) => s.toLowerCase() === text.trim().toLowerCase());
  if (!name) return false;
  if (!S.avoid.includes(name)) S.avoid.push(name);
  renderAvoid();
  return true;
}

/* ---------- planning ---------- */
function setStatus(html, kind = "warn") {
  const el = $("#status");
  el.hidden = !html;
  el.className = `status ${kind}`;
  el.innerHTML = html || "";
}

async function plan(e) {
  if (e) e.preventDefault();
  const spot = (key) => S[key] || { text: $(`#${key}`).value.trim() };
  const o = spot("origin"), d = spot("destination");
  if (!(o.text || o.lat) || !(d.text || d.lat)) {
    renderError("Enter where you're starting and where you're going.", "warn");
    return;
  }
  stopWatch();
  const btn = $("#planBtn");
  btn.disabled = true;
  btn.lastElementChild.textContent = "Planning…";
  $("#results").innerHTML = `<div class="skel-card"></div><div class="skel-card"></div><div class="skel-card"></div>`;
  const later = $("#leave").value === "later" && $("#departAt").value;
  try {
    const r = await api("/api/plan", {
      origin: o, destination: d, here: S.here, depart_at: later ? withOffset($("#departAt").value) : null,
      fewer_transfers: S.fewer, max_roll: +$("#maxRoll").value, avoid: S.avoid,
    });
    S.result = r;
    S.sel = 0;
    S.explainHTML = null;
    renderResults();
    if (r.ok && r.options.length) select(0, false);
    if (r.ok && r.changed) loadExplanation(r.id);
    $("#results").focus({ preventScroll: true });
  } catch (err) {
    renderError(err.message);
  } finally {
    btn.disabled = false;
    btn.lastElementChild.textContent = "Plan step-free trip";
  }
}

function renderError(msg, kind = "danger") {
  $("#results").innerHTML = `<div class="alert ${kind}">${icon("alert")}<div><h3>${kind === "warn" ? "Almost there" : "No trip yet"}</h3><p>${esc(msg)}</p></div></div>`;
  $("#detail").hidden = true;
}

function issueLine(p) {
  const note = p.note ? ` <em>(${esc(p.note)})</em>` : "";
  return `<li><strong>${esc(p.station)}</strong> (${esc(ROLE[p.role] || p.role)}): ${esc(p.alert)}${note}</li>`;
}

function cardHTML(opt, i) {
  const t = opt.trip, maxRoll = +$("#maxRoll").value;
  const role = opt.role === "recommended" ? `<span class="good">${S.result.changed ? "Recommended" : "Best trip"}</span>`
    : opt.role === "blocked" ? `<span class="bad">Usual trip · blocked</span>` : `<span>Option ${i + 1}</span>`;
  const long = t.longest_roll > maxRoll ? `<span class="sep"></span><span class="warn-t">${Math.round(t.longest_roll)}-min roll</span>` : "";
  const rides = t.legs.filter((l) => l.transit).filter((l, k, a) => k === 0 || a[k - 1].route_name !== l.route_name);
  return `<button type="button" class="card ${opt.role === "blocked" ? "blocked" : ""}" aria-pressed="${i === S.sel}" data-i="${i}">
    ${badge(t)}
    <span>
      <span class="card-title">${esc(clock(t.departs))} – ${esc(clock(t.arrives))}</span>
      <span class="card-sub">${role}<span class="sep"></span>${t.minutes} min<span class="sep"></span>${Math.round(t.rolling_minutes)} min rolling${long}</span>
      <span class="lines">${rides.map(linePill).join(`<span class="chev">${svg("chevron").replace("<svg", '<svg style="transform:rotate(-90deg)"')}</span>`) || "<span class='card-sub'>Roll the whole way</span>"}</span>
    </span>
    <span class="card-side">
      <span class="${opt.role === "blocked" ? "is-bad" : "is-ok"}" title="${opt.role === "blocked" ? "Blocked" : "Step-free, checked live"}">${icon(opt.role === "blocked" ? "alert" : "shield")}</span>
      ${t.live ? `<span title="Live times">${icon("live")}</span>` : ""}
    </span></button>`;
}

function renderResults() {
  const r = S.result, box = $("#results");
  if (!r.ok) {
    renderError(r.reason, r.stage === "places" ? "warn" : "danger");
    return;
  }
  let html = `<div class="section-title"><h2>${esc(r.origin.name)} → ${esc(r.dest.name)}</h2>
    <span>${r.depart_at ? "Leaving " + esc(clock(r.depart_at)) : "Leaving now"}</span></div>`;
  if (r.changed) {
    html += `<div class="alert danger">${icon("alert")}<div><h3>Your usual trip is blocked</h3>
      <ul>${r.problems.map(issueLine).join("")}</ul></div></div>`;
    if (!r.trip) html += `<div class="alert warn">${icon("info")}<div><h3>No step-free alternative right now</h3><p>${mdLite(r.explanation)}</p></div></div>`;
  } else {
    html += `<div class="alert ok">${icon("shield")}<div><h3>Clear right now</h3>
      <p>No elevator outages, stop changes or service problems affect this trip.</p></div></div>`;
  }
  html += r.options.map(cardHTML).join("");
  if (r.changed) {
    html += `<div class="explain" id="explain">${S.explainHTML || `<h3>${icon("sparkle")}Why this route</h3>
      <div class="skeleton w80"></div><div class="skeleton"></div><div class="skeleton w60"></div>`}</div>`;
  }
  box.innerHTML = html;
  box.querySelectorAll(".card").forEach((b) => b.addEventListener("click", () => select(+b.dataset.i)));
}

async function loadExplanation(id) {
  const my = ++S.explainSeq;
  let html;
  try {
    const e = await api(`/api/explain/${id}`, {});
    const chips = [...(e.sources || []).map((s) => `<span>${esc(s)}</span>`),
      ...(e.guardrails || []).map((g) => `<span>safety check: ${esc(g.replace(/_/g, " "))}</span>`)].join("");
    html = `<h3>${icon("sparkle")}Why this route</h3><div class="body">${mdLite(e.explanation)}</div>
      ${chips ? `<div class="meta-chips">${chips}</div>` : ""}`;
  } catch (err) {
    html = `<h3>${icon("sparkle")}Why this route</h3><div class="body">${mdLite(S.result.explanation)}</div>`;
  }
  if (my !== S.explainSeq) return;
  S.explainHTML = html;
  const box = $("#explain");
  if (box) box.innerHTML = html;
}

function select(i, scroll = true) {
  S.sel = i;
  document.querySelectorAll("#results .card").forEach((b) => b.setAttribute("aria-pressed", String(+b.dataset.i === i)));
  const opt = S.result.options[i];
  renderDetail(opt, i);
  drawTrip(opt.trip, S.result.origin, S.result.dest);
  if (scroll && window.innerWidth <= 900) $(".map-wrap").scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ---------- detail card ---------- */
function stepHTML(l) {
  if (l.mode === "ROLL") {
    const a = l.from.name, b = l.to.name;
    return `<li class="step roll"><span class="s-dot">${icon("wheelchair")}</span><div>
      <div class="s-main">Roll ${Math.max(1, Math.round(l.minutes))} min</div>
      <div class="s-sub">${a === b ? "Within " + esc(a) : esc(a) + " → " + esc(b)} · ${l.meters} m</div></div></li>`;
  }
  const c = colorOf(l);
  const timing = l.realtime ? `<span class="live">live</span>` : "scheduled";
  const late = l.delay_s >= 60 ? ` · <span class="late">${Math.round(l.delay_s / 60)} min late</span>` : "";
  return `<li class="step" style="--c:${c};--ink:${inkFor(c)}"><span class="s-dot">${icon(MODE_ICON[l.mode] || "bus")}</span><div>
    <div class="s-main">${esc(l.route_name)}${l.headsign ? " toward " + esc(l.headsign) : ""}</div>
    <div class="s-sub">${esc(l.from.name)} → ${esc(l.to.name)}</div>
    <div class="s-sub">Leaves ${esc(clock(l.start))} · ${timing}${late} · ${Math.round(l.minutes)} min</div></div></li>`;
}

function renderDetail(opt, i) {
  const t = opt.trip, el = $("#detail");
  const title = opt.role === "recommended" ? (S.result.changed ? "Recommended trip" : "Your trip")
    : opt.role === "blocked" ? "Usual trip (blocked)" : `Option ${i + 1}`;
  const issues = opt.role === "blocked" ? S.result.problems : [];
  const warnings = (t.check && t.check.warnings) || [];
  const w = S.watch && S.watch.option === i ? S.watch : null;
  let html = `<div class="d-head">${badge(t)}<div><div class="d-title">${esc(title)}</div>
      <div class="d-sub">Leave ${esc(clock(t.departs))} · arrive ${esc(clock(t.arrives))}</div></div></div>
    <div class="stats">
      <span class="stat">${icon("clock")}${t.minutes} min</span>
      <span class="stat">${icon("wheelchair")}${Math.round(t.rolling_minutes)} min</span>
      <span class="stat">${icon("transfer")}${plural(t.transfers, "change")}</span>
    </div>`;
  if (issues.length) html += `<div class="d-notes">${issues.map((p) => `<div class="note bad">${icon("alert")}<span><strong>${esc(p.station)}</strong>: ${esc(p.alert)}</span></div>`).join("")}</div>`;
  html += `<h3 class="d-h">Step by step</h3><ol class="steps">${t.legs.map(stepHTML).join("")}
    <li class="step"><span class="s-dot" style="background:#f4f5f7;color:#111">${icon("flag")}</span><div>
      <div class="s-main">Arrive at ${esc(S.result.dest.name)}</div><div class="s-sub">${esc(clock(t.arrives))}</div></div></li></ol>`;
  if (warnings.length) {
    html += `<details class="d-notes"><summary class="secondary" style="display:flex;align-items:center;gap:8px;list-style:none">${icon("info")}Good to know (${warnings.length})</summary>
      ${warnings.map((p) => `<div class="note">${icon("alert")}<span><strong>${esc(p.station)}</strong>: ${esc(p.alert)}${p.note ? ` (${esc(p.note)})` : ""}</span></div>`).join("")}</details>`;
  }
  if (opt.role !== "blocked") {
    if (!w) {
      html += `<button type="button" class="wide-btn" id="watchBtn">${icon("bell")}Start live monitoring</button>`;
    } else {
      html += `<div class="btn-row"><button type="button" class="wide-btn on" id="checkBtn">${icon("refresh")}Check now</button>
        <button type="button" class="wide-btn" id="simBtn">${icon("zap")}Simulate outage</button></div>
        <p class="disclaimer">Monitoring: checks live times and alerts every 2 minutes while this page is open.</p>
        <ul class="events">${w.events.map(eventHTML).join("")}</ul>`;
    }
  }
  html += `<p class="disclaimer">Rolling routes come from OpenStreetMap and may miss broken curb cuts or construction. Confirm at mbta.com/alerts/access.</p>`;
  el.innerHTML = html;
  el.hidden = false;
  $(".map-wrap").classList.add("has-detail");
  if (map) setTimeout(() => map.resize(), 0);
  const wb = $("#watchBtn"), cb = $("#checkBtn"), sb = $("#simBtn");
  if (wb) wb.addEventListener("click", startWatch);
  if (cb) cb.addEventListener("click", () => checkWatch(false));
  if (sb) sb.addEventListener("click", () => checkWatch(true));
}

function eventHTML(ev) {
  if (ev.error) return `<li class="event bad"><b>${esc(ev.time)}</b> ${esc(ev.error)}</li>`;
  if (ev.new_problems.length) {
    const what = ev.new_problems.map((p) => `${esc(p.station)}: ${esc(p.alert)}`).join("; ");
    const then = ev.switched ? "Switched you to a new step-free trip (shown on the map)." : "No better step-free trip right now.";
    return `<li class="event bad"><b>${esc(ev.time)} · New problem</b><br>${what}<br>${then}</li>`;
  }
  if (ev.resolved.length) return `<li class="event ok"><b>${esc(ev.time)} · Resolved</b><br>A problem on your trip was fixed.</li>`;
  return `<li class="event ok"><b>${esc(ev.time)}</b> No new problems. ${ev.live_times ? "Live times updated." : "Live times unavailable."}</li>`;
}

/* ---------- monitoring ---------- */
async function startWatch() {
  try {
    const r = await api("/api/monitor/start", { id: S.result.id, option: S.sel });
    if (!r.ok) throw new Error(r.reason || "Couldn't start monitoring");
    S.watch = { id: r.watch_id, option: S.sel, events: [] };
    S.timer = setInterval(() => checkWatch(false), 120000);
  } catch (err) {
    S.watch = { id: null, option: S.sel, events: [{ time: clock(new Date().toISOString()), error: err.message }] };
  }
  renderDetail(S.result.options[S.sel], S.sel);
}

async function checkWatch(simulate) {
  if (!S.watch || !S.watch.id) return;
  const btn = simulate ? $("#simBtn") : $("#checkBtn");
  if (btn) { btn.disabled = true; btn.lastChild.textContent = simulate ? "Replanning…" : "Checking…"; }
  try {
    const ev = await api(`/api/monitor/${S.watch.id}/check`, { simulate, here: S.here });
    S.watch.events.unshift(ev);
    if (ev.switched) S.result.options[S.watch.option].trip = ev.trip;
  } catch (err) {
    S.watch.events.unshift({ time: clock(new Date().toISOString()), error: err.message });
  }
  const watched = S.result.options[S.watch.option];
  const key = JSON.stringify(watched.trip.key);
  S.result.options = S.result.options.filter((o) => o === watched || JSON.stringify(o.trip.key) !== key);
  S.watch.option = S.result.options.indexOf(watched);
  const showing = S.sel === S.watch.option || S.sel >= S.result.options.length;
  if (showing) S.sel = S.watch.option;
  renderResults();
  if (showing) {
    renderDetail(watched, S.sel);
    drawTrip(watched.trip, S.result.origin, S.result.dest);
    const first = $("#detail .events li");
    if (first) first.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function stopWatch() {
  clearInterval(S.timer);
  S.timer = null;
  S.watch = null;
}

/* ---------- natural language ---------- */
async function understand() {
  const text = $("#nlText").value.trim();
  if (!text) return;
  const echo = $("#nlEcho"), btn = $("#nlGo");
  btn.disabled = true;
  echo.textContent = "Understanding your request…";
  try {
    const p = await api("/api/parse", { text });
    if (!p.origin || !p.destination) throw new Error("I couldn't tell where you're starting and going. Try “from <place> to <place>”.");
    for (const [key, val] of [["origin", p.origin], ["destination", p.destination]]) {
      if (val === p.current) {
        if (key === "origin") await locate();
        else throw new Error("Going to your own location isn't supported; type the destination.");
      } else {
        S[key] = null;
        $(`#${key}`).value = val;
      }
    }
    S.fewer = p.fewer_transfers;
    $("#fewerBtn").setAttribute("aria-pressed", String(S.fewer));
    if (p.max_roll) {
      const sel = $("#maxRoll");
      const best = [...sel.options].reduce((a, o) => Math.abs(o.value - p.max_roll) < Math.abs(a.value - p.max_roll) ? o : a);
      sel.value = best.value;
    }
    p.avoid.forEach(addAvoid);
    echo.textContent = `Understood: ${p.origin === p.current ? "your location" : p.origin} → ${p.destination}`
      + (p.fewer_transfers ? " · fewer transfers" : "") + (p.max_roll ? ` · rolls up to ${Math.round(p.max_roll)} min` : "")
      + (p.avoid.length ? ` · avoid ${p.avoid.join(", ")}` : "");
    await plan();
  } catch (err) {
    echo.textContent = err.message;
  } finally {
    btn.disabled = false;
  }
}

/* ---------- start ---------- */
async function boot() {
  hydrateIcons();
  initMap();
  setupField("origin");
  setupField("destination");
  $("#tripForm").addEventListener("submit", plan);
  $("#locateBtn").addEventListener("click", () => locate().catch((e) => renderError(e.message, "warn")));
  $("#swapBtn").addEventListener("click", () => {
    const o = $("#origin"), d = $("#destination");
    [o.value, d.value] = [d.value, o.value];
    [S.origin, S.destination] = [S.destination, S.origin];
  });
  $("#fewerBtn").addEventListener("click", (e) => {
    S.fewer = !S.fewer;
    e.currentTarget.setAttribute("aria-pressed", String(S.fewer));
  });
  $("#leave").addEventListener("change", (e) => {
    const later = e.target.value === "later";
    $("#laterBox").hidden = !later;
    if (later && !$("#departAt").value) {
      const d = new Date(Date.now() + 30 * 60000 - new Date().getTimezoneOffset() * 60000);
      $("#departAt").value = d.toISOString().slice(0, 16);
    }
  });
  $("#avoidBtn").addEventListener("click", (e) => {
    const open = $("#avoidBox").hidden;
    $("#avoidBox").hidden = !open;
    e.currentTarget.setAttribute("aria-expanded", String(open));
    if (open) $("#avoidInput").focus();
  });
  $("#avoidInput").addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    if (addAvoid(e.target.value)) e.target.value = "";
  });
  $("#avoidInput").addEventListener("change", (e) => { if (addAvoid(e.target.value)) e.target.value = ""; });
  $("#avoidTags").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (b) { S.avoid.splice(+b.dataset.i, 1); renderAvoid(); }
  });
  $("#nlGo").addEventListener("click", understand);
  $("#aboutBtn").addEventListener("click", () => $("#about").showModal());

  try {
    S.stations = await api("/api/stations");
    $("#stationList").innerHTML = S.stations.map((s) => `<option value="${esc(s)}">`).join("");
  } catch { /* station list is optional */ }
  try {
    const h = await api("/api/health");
    const msgs = [];
    if (!h.otp) msgs.push("The trip planner server isn't running. Start it with <code>py -3.12 otp/setup_otp.py serve</code>.");
    if (!h.mbta) msgs.push("No MBTA API key is set, so live data may be limited.");
    if (!h.db) msgs.push("Snowflake isn't connected: trips still work, but explanations use the data-only text.");
    setStatus(msgs.join("<br>"));
  } catch {
    setStatus("The TransitWise server isn't responding.");
  }
}

boot();
