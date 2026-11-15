/* Earth Evidence Atlas – frontend (vanilla JS, Leaflet, Plotly).
 * AI disclosure: generated with Claude (Anthropic) as a coding assistant; team review pending. */
"use strict";

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const ALL = "1,2,3,4,5,6,7,8,9,10,11,12";
const MIN_PERIOD_SPAN = 4; // five years including both endpoints

const state = { var: "ndvi", region: "central_europe", start: null, end: null, months: ALL, bbox: null };
let CAT = null, map = null, baseLayer = null, gridLayer = null, selLayer = null, regionLayer = null, lastMap = null;

// ---------------------------------------------------------------- colour maps (ColorBrewer)
const CMAPS = {
  RdBu_r: ["#053061", "#2166ac", "#4393c3", "#92c5de", "#d1e5f0", "#f7f7f7", "#fddbc7", "#f4a582", "#d6604d", "#b2182b", "#67001f"],
  BrBG: ["#543005", "#8c510a", "#bf812d", "#dfc27d", "#f6e8c3", "#f5f5f5", "#c7eae5", "#80cdc1", "#35978f", "#01665e", "#003c30"],
  Greys: ["#ffffff", "#f0f0f0", "#d9d9d9", "#bdbdbd", "#969696", "#737373", "#525252", "#252525"],
};
function hex(h) { return [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)); }
function colorAt(stops, x) { // x in [0,1]
  x = Math.max(0, Math.min(1, x));
  const f = x * (stops.length - 1), i = Math.min(Math.floor(f), stops.length - 2), t = f - i;
  const a = hex(stops[i]), b = hex(stops[i + 1]);
  return `rgb(${a.map((v, k) => Math.round(v + (b[k] - v) * t)).join(",")})`;
}
const fmt = (x, d = 3) => (x === null || x === undefined || !isFinite(x)) ? "–" :
  (Math.abs(x) >= 100 ? I18N.number(x, { maximumFractionDigits: 0 }) : I18N.number(Number(x.toPrecision(d)), { maximumSignificantDigits: d }));
const fmtP = (p) => p === null || p === undefined ? "–" : p < 0.001 ? `< ${I18N.number(0.001)}` : I18N.number(p, { minimumFractionDigits: 3, maximumFractionDigits: 3 });
const pStr = (p) => p === null || p === undefined ? t("common.pValueUnavailable") : p < 0.001 ? t("common.pValueBelow", { value: I18N.number(0.001) }) : t("common.pValue", { value: fmtP(p) });
const plotCfg = { displaylogo: false, responsive: true, displayModeBar: false };
const dark = () => matchMedia("(prefers-color-scheme: dark)").matches;
function layoutBase(extra) {
  // axes are merged key by key, so a chart can add a title without losing the theme colours
  const ink = getComputedStyle(document.body).color, grid = dark() ? "#2a3542" : "#e8edf2";
  const base = {
    margin: { l: 56, r: 12, t: 8, b: 36 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "system-ui, sans-serif", size: 12, color: ink }, autosize: true,
    xaxis: { gridcolor: grid, linecolor: grid, zeroline: false, automargin: true, spikecolor: dark() ? "#4b5a6a" : "#9aa7b4", spikethickness: 1, spikedash: "solid" },
    yaxis: { gridcolor: grid, linecolor: grid, zerolinecolor: dark() ? "#4b5a6a" : "#9aa7b4", automargin: true },
    legend: { orientation: "h", y: -0.18 }, hovermode: "x unified",
    hoverlabel: { bgcolor: "#0f1720", bordercolor: "#2a3542", font: { color: "#e6edf3" } },
  };
  const e = extra || {};
  const out = Object.assign({}, base, e);
  ["xaxis", "yaxis"].forEach((k) => { out[k] = Object.assign({}, base[k], e[k] || {}); });
  if (e.margin) out.margin = Object.assign({}, base.margin, e.margin);
  return out;
}
// keep every chart sized to its box (tabs, panels and window resizes)
const chartObserver = new ResizeObserver((entries) => entries.forEach((en) => {
  const el = en.target;
  if (el.data && el.offsetParent !== null && en.contentRect.width > 0) Plotly.Plots.resize(el);
}));
// the Leaflet map grows with its card, so tell it when its box changes size
const mapObserver = new ResizeObserver(() => { if (map && $("#map").offsetParent !== null) map.invalidateSize(); });
function watchCharts() { $$(".chart").forEach((el) => chartObserver.observe(el)); }
function setHeaderHeight() { document.documentElement.style.setProperty("--hdr", $(".top").offsetHeight + "px"); }

// ---------------------------------------------------------------- one tooltip style for the whole app
const ic = (name, cls = "") => `<svg class="ic ${cls}"><use href="/static/icons.svg#i-${name}"/></svg>`;
function showTip(html, x, y) {
  const t = $("#tip");
  t.innerHTML = html; t.hidden = false;
  const r = t.getBoundingClientRect(), W = innerWidth, H = innerHeight;
  let left = x + 14, top = y + 14;
  if (left + r.width > W - 8) left = x - r.width - 14;
  if (top + r.height > H - 8) top = y - r.height - 14;
  t.style.left = Math.max(8, left) + "px"; t.style.top = Math.max(8, top) + "px";
}
function hideTip() { $("#tip").hidden = true; }
function wireTips(root = document) {
  // [data-tip] = short label, [data-tiphtml] = rich text set by code
  root.addEventListener("mouseover", (e) => {
    const el = e.target.closest("[data-tip],[data-tiphtml]");
    if (!el) return;
    const r = el.getBoundingClientRect();
    showTip(el.dataset.tiphtml || el.dataset.tip, r.left, r.bottom - 6);
  });
  root.addEventListener("mouseout", (e) => { if (e.target.closest("[data-tip],[data-tiphtml]")) hideTip(); });
  root.addEventListener("focusin", (e) => {
    const el = e.target.closest("[data-tip],[data-tiphtml]");
    if (el) { const r = el.getBoundingClientRect(); showTip(el.dataset.tiphtml || el.dataset.tip, r.left, r.bottom - 6); }
  });
  root.addEventListener("focusout", hideTip);
}
const monthLabel = (month, form = "short") => t(`calendar.months.${month}.${form}`);
function fmtX(x) {
  const m = /^(\d{4})-(\d{2})/.exec(String(x));
  return m ? `${monthLabel(+m[2])} ${m[1]}` : String(x);
}
function defaultTip(ev) {
  const pts = ev.points.filter((p) => p.data.hoverinfo !== "skip");
  if (!pts.length) return "";
  const p0 = pts[0];
  if (p0.data.type === "heatmap") return p0.text || "";
  if (p0.customdata !== undefined && p0.data.type === "bar") return `<b>${p0.x}</b><br>${p0.customdata}`;
  const rows = pts.map((p) => {
    const c = (p.data.line && p.data.line.color) || (p.data.marker && p.data.marker.color) || "#8aa4bf";
    return `<div class="trow"><i style="background:${Array.isArray(c) ? c[p.pointNumber] : c}"></i>${p.data.name || ""}<b>${fmt(p.y)}</b></div>`;
  }).join("");
  return `<div class="thead">${fmtX(p0.x)}</div>${rows}`;
}
// Plotly with the app's own tooltip (Plotly's built-in hover labels are switched off)
const plotLocales = new Set();
function plot(id, traces, layout, tipFn = defaultTip) {
  if (!plotLocales.has(I18N.language)) {
    const parts = new Intl.NumberFormat(I18N.language).formatToParts(1234.5);
    Plotly.register({ moduleType: "locale", name: I18N.language, dictionary: {}, format: {
      months: Array.from({ length: 12 }, (_, i) => monthLabel(i + 1, "full")),
      shortMonths: Array.from({ length: 12 }, (_, i) => monthLabel(i + 1)),
      days: Array.from({ length: 7 }, (_, i) => t(`calendar.weekdays.${i}.full`)),
      shortDays: Array.from({ length: 7 }, (_, i) => t(`calendar.weekdays.${i}.short`)),
      periods: [t("calendar.periods.am"), t("calendar.periods.pm")],
      dateTime: t("calendar.formats.dateTime"), date: t("calendar.formats.date"), time: t("calendar.formats.time"),
      year: t("calendar.formats.year"), month: t("calendar.formats.month"),
      dayMonth: t("calendar.formats.dayMonth"), dayMonthYear: t("calendar.formats.dayMonthYear"),
      grouping: [3], currency: ["$", ""],
      decimal: parts.find((part) => part.type === "decimal").value,
      thousands: (parts.find((part) => part.type === "group") || { value: "" }).value,
    } });
    plotLocales.add(I18N.language);
  }
  plotCfg.locale = I18N.language;
  const el = typeof id === "string" ? document.getElementById(id) : id;
  traces.forEach((t) => { if (t.hoverinfo !== "skip") { t.hoverinfo = "none"; delete t.hovertemplate; } });
  const res = Plotly.react(el, traces, layout, plotCfg);
  if (!el._tipBound) {
    el._tipBound = true;
    el.on("plotly_hover", (ev) => { const h = (el._tipFn || defaultTip)(ev); if (h) showTip(h, ev.event.clientX, ev.event.clientY); else hideTip(); });
    el.on("plotly_unhover", hideTip);
    el.addEventListener("mouseleave", hideTip);
  }
  el._tipFn = tipFn;
  return res;
}
// ---------------------------------------------------------------- logo sparkle: one star at a time on the glyph edges
async function initLogoSpark() {
  const h = $("#logo"), txt = h.querySelector(".logo-text"), sp = h.querySelector(".spark");
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  try { await document.fonts.load('20px "Nasalization"'); } catch (e) { /* fall back to the system font outline */ }
  let pts = [], ox = 0, oy = 0;
  const sample = () => {
    const cs = getComputedStyle(h), r = txt.getBoundingClientRect(), hr = h.getBoundingClientRect();
    const W = Math.ceil(r.width) + 8, H = Math.ceil(r.height) + 8;
    const cv = document.createElement("canvas"); cv.width = W; cv.height = H;
    const ctx = cv.getContext("2d");
    ctx.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
    if ("letterSpacing" in ctx) ctx.letterSpacing = cs.letterSpacing;
    ctx.textBaseline = "middle"; ctx.fillText(txt.textContent, 4, H / 2);
    const d = ctx.getImageData(0, 0, W, H).data, A = (x, y) => d[(y * W + x) * 4 + 3] > 110;
    pts = [];
    for (let y = 1; y < H - 1; y++) for (let x = 1; x < W - 1; x++)
      if (A(x, y) && (!A(x - 1, y) || !A(x + 1, y) || !A(x, y - 1) || !A(x, y + 1))) pts.push([x - 4, y]);
    ox = r.left - hr.left; oy = r.top - hr.top + (r.height - H) / 2;
  };
  sample(); addEventListener("resize", sample);
  const next = () => {
    if (!pts.length) return;
    const [x, y] = pts[Math.floor(Math.random() * pts.length)];
    sp.style.left = ox + x + "px"; sp.style.top = oy + y + "px";
    sp.classList.remove("go"); void sp.offsetWidth; sp.classList.add("go");
  };
  sp.addEventListener("animationend", () => setTimeout(next, 250 + Math.random() * 1100));
  setTimeout(next, 600);
}
// ---------------------------------------------------------------- user-made areas: which ones this visitor sees
// Areas are shared on the server, so nothing is deleted from here: a visitor sees the areas they made,
// can hide any of them, and can opt in to areas made by others. Built-in regions are always shown.
function lsGet(k, d) { try { const v = JSON.parse(localStorage.getItem(k)); return v === null ? d : v; } catch (e) { return d; } }
function lsSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode: keep defaults */ } }
const AREAS = {
  mine: () => lsGet("atlas.myAreas", []),
  hidden: () => lsGet("atlas.hiddenAreas", []),
  others: () => lsGet("atlas.showOthers", false),
  add(id) { if (!id || !id.startsWith("c_")) return; lsSet("atlas.myAreas", [...new Set([...AREAS.mine(), id])]); lsSet("atlas.hiddenAreas", AREAS.hidden().filter((x) => x !== id)); },
  hide(id) { lsSet("atlas.hiddenAreas", [...new Set([...AREAS.hidden(), id])]); },
  setOthers(on) { lsSet("atlas.showOthers", !!on); },
  visible(id) { return !id.startsWith("c_") || (!AREAS.hidden().includes(id) && (AREAS.mine().includes(id) || AREAS.others())); },
};
function setPressed(btn, on) { btn.classList.toggle("on", on); btn.setAttribute("aria-pressed", on ? "true" : "false"); }
const pressed = (btn) => btn.getAttribute("aria-pressed") === "true";

// ---------------------------------------------------------------- URL state
function readHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  ["var", "region", "months"].forEach((k) => { if (h.get(k)) state[k] = h.get(k); });
  ["start", "end"].forEach((k) => { if (h.get(k)) state[k] = +h.get(k); });
  if (h.get("bbox")) state.bbox = h.get("bbox").split(",").map(Number);
}
function writeHash() {
  history.replaceState(null, "", "#" + query(true));
}
function query(withBbox) {
  const p = new URLSearchParams({ var: state.var, region: state.region, start: state.start, end: state.end, months: state.months });
  if (withBbox && state.bbox) p.set("bbox", state.bbox.map((x) => +x.toFixed(3)).join(","));
  return p.toString();
}
async function api(path, params) {
  const r = await fetch(`/api/${path}?${params}`);
  if (!r.ok) throw new Error(I18N.text((await r.json().catch(() => ({}))).detail || r.statusText));
  return I18N.response(path, await r.json());
}

// ---------------------------------------------------------------- controls
function V() { return CAT.variables.find((v) => v.id === state.var); }
function available(v, r) { return !!CAT.available[`${v}/${r}`]; }

function buildVarCards() {
  $("#varCards").innerHTML = CAT.variables.map((v) =>
    `<button class="vcard" data-v="${v.id}" data-tiphtml="${v.definition.replace(/"/g, "&quot;")}">${v.question}<b>${v.name.replace(/ \(.*\)/, "")}</b></button>`).join("");
  $$(".vcard").forEach((b) => b.onclick = () => {
    state.var = b.dataset.v;
    const v = V();
    if (!v.regions.includes(state.region) || !available(v.id, state.region)) {
      state.region = v.regions.find((r) => available(v.id, r)) || v.regions[0];
    }
    state.start = state.end = null; state.bbox = null;
    syncControls(); refresh(true);
    // bring the answer into view if it is below the fold
    const r = $("#answer").getBoundingClientRect();
    if (r.top > innerHeight - 120 || r.bottom < 0) $("#answer").scrollIntoView({ behavior: "smooth", block: "center" });
  });
}
function syncControls() {
  const v = V();
  $$(".vcard").forEach((b) => {
    b.classList.toggle("on", b.dataset.v === state.var);
    const vv = CAT.variables.find((x) => x.id === b.dataset.v);
    b.disabled = !vv.regions.some((r) => available(vv.id, r));
  });
  const regs = v.regions.concat(CAT.regions.filter((r) => r.custom && available(v.id, r.id) && AREAS.visible(r.id)).map((r) => r.id));
  if (!regs.includes(state.region)) regs.push(state.region);
  $("#region").innerHTML = regs.map((r) => {
    const R = CAT.regions.find((x) => x.id === r);
    return `<option value="${r}" ${available(v.id, r) ? "" : "disabled"}>${R.name}${available(v.id, r) ? "" : t("common.noDataSuffix")}</option>`;
  }).join("");
  $("#region").value = state.region;
  $("#regionStory").textContent = CAT.regions.find((x) => x.id === state.region).story;
  $("#hideArea").hidden = !state.region.startsWith("c_");
  $("#showOthers").checked = AREAS.others();
  const [y0, y1] = v.years;
  const lastStart = y1 - MIN_PERIOD_SPAN, firstEnd = y0 + MIN_PERIOD_SPAN;
  state.start = Math.max(y0, Math.min(lastStart, state.start || y0));
  state.end = Math.max(state.start + MIN_PERIOD_SPAN, Math.min(y1, state.end || y1));
  const opts = (min, max, sel) => Array.from({ length: max - min + 1 }, (_, i) => min + i)
    .map((y) => `<option ${y === sel ? "selected" : ""}>${y}</option>`).join("");
  $("#start").innerHTML = opts(y0, lastStart, state.start);
  $("#end").innerHTML = opts(firstEnd, y1, state.end);
  ["#startSlider", "#endSlider"].forEach((id) => Object.assign($(id), { min: y0, max: y1 }));
  $("#firstYear").textContent = y0;
  $("#lastYear").textContent = y1;
  syncPeriodRange();
  $$(".seasons .chip").forEach((c) => c.classList.toggle("on", c.dataset.m === state.months));
  $("#resetSel").hidden = !state.bbox;
  $("#resetSel").classList.toggle("on", false);
  $("#selInfo").textContent = state.bbox ? t("detective.areaCoordinates", { coordinates: state.bbox.map((x) => I18N.number(x, { minimumFractionDigits: 1, maximumFractionDigits: 1 })).join("; ") }) :
    t("detective.wholeRegionHint");
}
function updatePeriodYears(which, year) {
  const [first, last] = V().years;
  if (which === "start") {
    state.start = Math.min(year, last - MIN_PERIOD_SPAN);
    state.end = Math.max(state.end, state.start + MIN_PERIOD_SPAN);
  } else {
    state.end = Math.max(year, first + MIN_PERIOD_SPAN);
    state.start = Math.min(state.start, state.end - MIN_PERIOD_SPAN);
  }
  syncPeriodRange();
}
function syncPeriodRange() {
  const [first, last] = V().years;
  $("#start").value = $("#startSlider").value = state.start;
  $("#end").value = $("#endSlider").value = state.end;
  const axis = $("#periodRange");
  axis.style.setProperty("--start", `${100 * (state.start - first) / (last - first)}%`);
  axis.style.setProperty("--end", `${100 * (state.end - first) / (last - first)}%`);
}
function wireControls() {
  $("#region").onchange = (e) => { state.region = e.target.value; state.bbox = null; syncControls(); refresh(true); };
  $("#hideArea").onclick = () => {
    AREAS.hide(state.region); hideTip();
    const v = V(); state.region = v.regions.find((r) => available(v.id, r)) || v.regions[0]; state.bbox = null;
    syncControls(); refresh(true);
    if (window.refreshGlobeAreas) window.refreshGlobeAreas();
  };
  $("#showOthers").onchange = (e) => { AREAS.setOthers(e.target.checked); syncControls(); if (window.refreshGlobeAreas) window.refreshGlobeAreas(); };
  ["start", "end"].forEach((which) => {
    $(`#${which}`).onchange = (e) => { updatePeriodYears(which, +e.target.value); refresh(false); };
    const slider = $(`#${which}Slider`);
    slider.oninput = (e) => updatePeriodYears(which, +e.target.value);
    slider.onchange = () => refresh(false);
  });
  $("#periodRange").onclick = (e) => {
    if (e.target.matches("input")) return;
    const track = $(".period-track").getBoundingClientRect();
    const [first, last] = V().years;
    const fraction = Math.max(0, Math.min(1, (e.clientX - track.left) / track.width));
    const year = Math.round(first + fraction * (last - first));
    const which = Math.abs(year - state.start) <= Math.abs(year - state.end) ? "start" : "end";
    updatePeriodYears(which, year);
    $(`#${which}Slider`).focus();
    refresh(false);
  };
  $$(".seasons .chip").forEach((c) => c.onclick = () => { state.months = c.dataset.m; syncControls(); refresh(false); });
  $("#resetSel").onclick = () => { state.bbox = null; syncControls(); drawSelection(); refreshAnalysis(); };
  ["#sigOnly", "#showCoverage"].forEach((sel) => $(sel).onclick = () => { setPressed($(sel), !pressed($(sel))); lastMap && drawGrid(lastMap); });
  $("#copyLink").onclick = () => {
    const b = $("#copyLink");
    navigator.clipboard && navigator.clipboard.writeText(location.href);
    b.innerHTML = `${ic("check")}<span>${t("common.copied")}</span>`;
    setTimeout(() => { b.innerHTML = `${ic("link")}<span>${t("common.copyLink")}</span>`; }, 1500);
  };
  $$(".tab").forEach((t) => t.onclick = () => {
    $$(".tab").forEach((x) => x.classList.toggle("active", x === t));
    $$(".panel").forEach((p) => p.classList.toggle("active", p.id === t.dataset.tab));
    document.body.classList.toggle("on-globe", t.dataset.tab === "globe");
    if (t.dataset.tab === "lab") { simOne(); if (!spikeExample) loadSpikeExample(); }
    if (t.dataset.tab === "atlas") { map.invalidateSize(); drawRegion(); drawSelection(); }
    window.dispatchEvent(new Event("resize"));
    requestAnimationFrame(() => $$(`#${t.dataset.tab} .chart`).forEach((el) => { if (el.data) Plotly.Plots.resize(el); }));
  });
}

// ---------------------------------------------------------------- map
function initMap() {
  map = L.map("map", { preferCanvas: true, worldCopyJump: false, minZoom: 1, zoomControl: false });
  L.control.zoom({ zoomInTitle: t("mapControls.zoomIn"), zoomOutTitle: t("mapControls.zoomOut") }).addTo(map);
  mapObserver.observe($("#map"));
  // NASA GIBS basemap (no API key): Blue Marble relief + reference coastlines/borders/labels on top of the data
  const GIBS = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/";
  baseLayer = L.tileLayer(GIBS + "BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg", {
    attribution: t("detective.basemapAttribution", { source: '<a href="https://earthdata.nasa.gov/gibs" target="_blank" rel="noopener">NASA GIBS</a>' }),
    maxNativeZoom: 8, maxZoom: 11,
  }).addTo(map);
  // tools on the map itself: select an area / back to the whole region, plus a banner while selecting
  const Tools = L.Control.extend({
    options: { position: "topright" },
    onAdd() {
      const d = L.DomUtil.create("div", "maptool");
      d.innerHTML = `<button id="drawBtn" class="btn ghost" aria-pressed="false" data-tiphtml="${esc(t("detective.selectAreaTooltipHtml"))}">${ic("select")}<span>${t("common.selectArea")}</span></button>` +
        `<button id="resetSel" class="ibtn" hidden aria-label="${esc(t("detective.wholeRegion"))}" data-tip="${esc(t("detective.resetSelectionHint"))}">${ic("expand")}</button>`;
      L.DomEvent.disableClickPropagation(d); L.DomEvent.disableScrollPropagation(d);
      return d;
    },
  });
  new Tools().addTo(map);
  const banner = L.DomUtil.create("div", "drawbanner", map.getContainer());
  banner.hidden = true;
  banner.innerHTML = `${ic("select")}<span>${t("detective.dragToSelect")}</span><button class="btn ghost small">${t("common.cancel")}</button>`;
  L.DomEvent.disableClickPropagation(banner);
  let drawing = false, startLL = null, rect = null, justDrew = 0;
  const setDraw = (on) => {
    drawing = on; setPressed($("#drawBtn"), on);
    $("#map").classList.toggle("drawing", on); banner.hidden = !on;
    on ? map.dragging.disable() : map.dragging.enable();
    hideTip();
    if (!on && rect) { map.removeLayer(rect); rect = null; }
  };
  $("#drawBtn").onclick = () => setDraw(!drawing);
  banner.querySelector("button").onclick = () => setDraw(false);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && drawing) setDraw(false); });
  map.on("mousedown", (e) => { if (!drawing || e.originalEvent.button !== 0 || rect) return; startLL = e.latlng; rect = L.rectangle([startLL, startLL], { color: "#ffd166", weight: 2, fill: true, fillOpacity: 0.12, dashArray: "4", interactive: false }).addTo(map); });
  map.on("mousemove", (e) => { if (drawing && rect) rect.setBounds([startLL, e.latlng]); });
  map.on("mouseup", (e) => {
    if (!drawing || !rect) return;
    const b = L.latLngBounds(startLL, e.latlng);
    setDraw(false); justDrew = Date.now(); // the click that ends a drag must not also select a cell
    if (b.getEast() - b.getWest() < 1e-3 || b.getNorth() - b.getSouth() < 1e-3) return;
    state.bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
    syncControls(); drawSelection(); refreshAnalysis();
  });
  // hover / click on the data grid (drawn as one image, so the cell is found from the cursor position)
  const cellAt = (ll) => {
    const m = lastMap; if (!m || !gridLayer) return null;
    const dlat = m.lat.length > 1 ? Math.abs(m.lat[1] - m.lat[0]) : 2, dlon = m.lon.length > 1 ? Math.abs(m.lon[1] - m.lon[0]) : 2;
    const i = Math.round((ll.lat - Math.min(...m.lat)) / dlat), j = Math.round((ll.lng - Math.min(...m.lon)) / dlon);
    return i >= 0 && i < m.lat.length && j >= 0 && j < m.lon.length ? { m, i, j, dlat, dlon } : null;
  };
  map.on("mousemove", (e) => {
    if (drawing) { hideTip(); return; }
    const c = cellAt(e.latlng);
    if (!c) { hideTip(); $("#map").classList.remove("oncell"); return; }
    const { m, i, j } = c, s = m.slope[i][j], vf = m.valid_fraction[i][j], sig = m.sig_fdr[i][j];
    $("#map").classList.add("oncell");
    showTip(s === null ? t("detective.tooFewData", { percent: Math.round(vf * 100) }) :
      `<b>${s > 0 ? "+" : ""}${fmt(s)}</b> ${m.trend_units}<br><span class="muted">${pStr(m.p[i][j])} · ${sig ? t("common.significant") : t("common.notSignificant")} · ${t("common.dataPercent", { percent: Math.round(vf * 100) })}</span>`,
    e.originalEvent.clientX, e.originalEvent.clientY);
  });
  map.on("mouseout", hideTip);
  map.on("click", (e) => {
    if (drawing || Date.now() - justDrew < 400) return;
    const c = cellAt(e.latlng); if (!c) return;
    const la = c.m.lat[c.i], lo = c.m.lon[c.j];
    state.bbox = [lo - c.dlon / 2, la - c.dlat / 2, lo + c.dlon / 2, la + c.dlat / 2];
    syncControls(); drawSelection(); refreshAnalysis();
  });
}
function drawRegion() {
  if (regionLayer) map.removeLayer(regionLayer);
  const [w, s, e, n] = CAT.regions.find((r) => r.id === state.region).bbox;
  regionLayer = L.rectangle([[s, w], [n, e]], { color: "#0b5cad", weight: 1, fill: false, interactive: false }).addTo(map);
  map.fitBounds([[Math.max(s, -60), w], [Math.min(n, 75), e]], { padding: [10, 10] });
}
function drawSelection() {
  if (selLayer) { map.removeLayer(selLayer); selLayer = null; }
  if (!state.bbox) return;
  const [w, s, e, n] = state.bbox;
  selLayer = L.rectangle([[s, w], [n, e]], { color: "#111", weight: 2.5, fill: false, interactive: false }).addTo(map);
}
function drawGrid(m) {
  lastMap = m;
  if (gridLayer) map.removeLayer(gridLayer);
  const v = V(), stops = CMAPS[v.colormap] || CMAPS.RdBu_r;
  const lim = m.color_limit || 1, cov = pressed($("#showCoverage")), fade = pressed($("#sigOnly"));
  // one Mercator-correct image for the whole grid: crisp at every zoom, no seams between cells
  const rgba = (css, op) => { const k = css.match(/\d+/g).map(Number); return `${k[0]},${k[1]},${k[2]},${Math.round(op * 255)}`; };
  const vals = m.lat.map((_, i) => m.lon.map((__, j) => {
    const s = m.slope[i][j], vf = m.valid_fraction[i][j], sig = m.sig_fdr[i][j];
    if (cov) return rgba(colorAt(CMAPS.Greys, 1 - vf), 0.8);
    if (s === null) return "154,160,166,90";
    return rgba(colorAt(stops, 0.5 + s / (2 * lim)), fade && !sig ? 0.15 : 0.8);
  }));
  const im = gridImage(m.lat, m.lon, vals, (x) => x.split(",").map(Number));
  const [[w, n], , [e, s]] = im.coords;
  gridLayer = L.imageOverlay(im.url, [[s, w], [n, e]], { className: "gridimg", interactive: false }).addTo(map);
  if (regionLayer) regionLayer.bringToFront();
  drawLegend(m, stops, lim, cov);
  const S = m.summary;
  $("#mapSummary").innerHTML = cov ? t("detective.coverageSummary") :
    th("detective.mapSummary", { positive: S.positive, negative: S.negative, significant: S.significant_fdr, total: S.cells_with_trend }) +
    ` <span data-tip="${esc(t("detective.fdrHint", { q: I18N.number(m.fdr_q), uncorrected: S.significant_uncorrected }))}">(FDR)</span>`;
}
function drawLegend(m, stops, lim, cov) {
  if (cov) {
    $("#legend").innerHTML = `<span>0%</span><span class="bar" style="background:linear-gradient(90deg,${CMAPS.Greys.join(",")})"></span><span>${t("common.dataPercent", { percent: 100 })}</span>`;
    return;
  }
  const grad = Array.from({ length: 11 }, (_, k) => colorAt(stops, k / 10)).join(",");
  $("#legend").innerHTML = `<span>${fmt(-lim, 2)}</span><span class="bar" style="background:linear-gradient(90deg,${grad})"></span>` +
    `<span>+${fmt(lim, 2)} ${m.trend_units}</span><span class="nd"></span><span>${t("common.noData")}</span>`;
}

// ---------------------------------------------------------------- result card + charts
function renderAnswer(a) {
  const A = a.answer;
  $("#answer").classList.remove("loading");
  if (!A || A.code === "error") {
    $("#answerQ").textContent = V().question;
    $("#answerBody").innerHTML = `<p class="hint">${A && A.note ? th("detective.noAnswerWithNote", { note: A.note }) : t("detective.noAnswer")}</p>`;
    return;
  }
  $("#answer").dataset.code = A.code;
  $("#answerQ").textContent = A.question;
  $("#answerBody").innerHTML = `
    <p class="answer-head">${A.headline}</p>
    <ul class="answer-lines">${A.lines.map((l) => `<li>${l}</li>`).join("")}</ul>
    ${A.caveat ? `<p class="answer-caveat">${ic("info")}<span>${A.caveat}${A.source_url ? ` <a href="${esc(A.source_url)}" target="_blank" rel="noopener">${t("detective.precipitationSource")}</a>` : ""}</span></p>` : ""}
    <details class="answer-how"><summary>${t("detective.howWeKnow")}</summary><ul>${A.how.map((l) => `<li>${l}</li>`).join("")}</ul>
      <p class="hint">${A.note}</p></details>`;
}
function answerLoading() {
  $("#answer").classList.add("loading");
  $("#answerQ").textContent = V().question;
}
function renderCard(a) {
  const r = a.result, v = V(), ver = a.verdict;
  const rob = ver.robustness ? `<div><span>${t("detective.otherPeriodsAgree")}</span>${ver.robustness.same_sign} / ${ver.robustness.windows}</div>` : "";
  const season = { [ALL]: t("calendar.allYear"), "12,1,2": t("calendar.seasons.djf.label"), "3,4,5": t("calendar.seasons.mam.label"), "6,7,8": t("calendar.seasons.jja.label"), "9,10,11": t("calendar.seasons.son.label") }[state.months] || t("calendar.selectedMonths");
  $("#card").innerHTML = `
    <div class="verdict ${ver.code}"><h2>${a.answer.source_url && ver.code === "trend_detected" ? t("detective.significantInMerra") : ver.title}</h2><p>${ver.text}</p></div>
    <div class="big">${r.slope > 0 ? "+" : ""}${fmt(r.slope)} <small>${a.trend_units}</small></div>
    <div class="hint">${th("detective.confidenceRange", { low: fmt(r.ci_low), high: fmt(r.ci_high), start: a.start, end: a.end, season })}</div>
    <div class="stats">
      <div data-tip="${esc(t("detective.pValueHint"))}"><span>${t("detective.pValue")}</span>${fmtP(r.p)}</div>
      <div data-tip="${esc(t("detective.mannKendallHint"))}"><span>${t("detective.mannKendallP")}</span>${fmtP(r.mk_p)}</div>
      <div data-tip="${esc(t("detective.senSlopeHint"))}"><span>${t("detective.senSlope")}</span>${fmt(r.sen_slope)}</div>
      <div data-tip="${esc(t("detective.effectiveNHint"))}"><span>${t("detective.effectiveN")}</span>${r.n} / ${Math.round(r.n_eff)}</div>
      <div data-tip="${t(a.cells === 1 ? "detective.gridCellsHintOne" : "detective.gridCellsHint", { count: a.cells })}"><span>${t("detective.validData")}</span>${Math.round(r.valid_fraction * 100)}%</div>
      ${rob}
    </div>`;
}
function renderChart(a) {
  const s = a.series, r = a.result, v = V();
  const x = s.dates.map((d) => d + "-15");
  // trend fan: lines with the CI-bound slopes, pivoting at the mean time
  const lo = s.t.map((t, i) => s.fit[i] + (r.ci_low - r.slope) / 10 * (t - s.t_mean));
  const hi = s.t.map((t, i) => s.fit[i] + (r.ci_high - r.slope) / 10 * (t - s.t_mean));
  const traces = [
    { x, y: s.anomaly, type: "scatter", mode: state.months === ALL ? "lines" : "markers", name: t("charts.month"),
      line: { color: "#8aa4bf", width: 1 }, marker: { size: 4, color: "#8aa4bf" } },
  ];
  if (s.running12) traces.push({ x, y: s.running12, type: "scatter", mode: "lines", name: t("charts.runningMean"), line: { color: dark() ? "#5ea8ff" : "#0b5cad", width: 2 } });
  traces.push(
    { x, y: hi, type: "scatter", mode: "lines", line: { width: 0 }, showlegend: false, hoverinfo: "skip" },
    { x, y: lo, type: "scatter", mode: "lines", fill: "tonexty", fillcolor: "rgba(214,96,77,.18)", line: { width: 0 }, name: t("charts.confidenceRange"), hoverinfo: "skip" },
    { x, y: s.fit, type: "scatter", mode: "lines", name: t("charts.trend"), line: { color: "#d6604d", width: 2.5 } },
  );
  plot("chart", traces, layoutBase({ yaxis: { title: { text: t("charts.anomalyAxis", { unit: v.units.replace(/ \(.*\)/, "") }), font: { size: 12 } } } }));
}
function renderMatrix(a) {
  const mx = a.matrix;
  if (!mx) { Plotly.purge("matrix"); $("#matrixNote").textContent = t("charts.minimumMatrixPeriod"); return; }
  const z = mx.ends.map((e) => mx.starts.map((s) => { const c = mx.cells.find((c) => c.start === s && c.end === e); return c ? c.slope : null; }));
  const sig = mx.ends.map((e) => mx.starts.map((s) => { const c = mx.cells.find((c) => c.start === s && c.end === e); return c && c.p !== null ? (c.p < 0.05 ? "●" : "") : ""; }));
  const text = mx.ends.map((e) => mx.starts.map((s) => { const c = mx.cells.find((c) => c.start === s && c.end === e); return c && c.slope !== null ? `<div class="thead">${s}–${e}</div><b>${c.slope > 0 ? "+" : ""}${fmt(c.slope)}</b> ${a.trend_units}<br><span class="muted">${pStr(c.p)}</span>` : ""; }));
  const lim = Math.max(...mx.cells.filter((c) => c.slope !== null).map((c) => Math.abs(c.slope)), 1e-9);
  const stops = CMAPS[V().colormap] || CMAPS.RdBu_r;
  const cs = stops.map((c, i) => [i / (stops.length - 1), c]);
  const tk = $("#matrix").clientWidth < 520 ? 4 : 2; // fewer year labels on narrow screens
  plot("matrix", [{
    type: "heatmap", x: mx.starts, y: mx.ends, z, text, hoverinfo: "text", colorscale: cs, zmin: -lim, zmax: lim,
    colorbar: { title: { text: a.trend_units, side: "right" }, thickness: 10, outlinewidth: 0 }, xgap: 1, ygap: 1,
  }, {
    type: "scatter", mode: "text", x: mx.ends.flatMap(() => mx.starts), y: mx.ends.flatMap((e) => mx.starts.map(() => e)),
    text: sig.flat(), hoverinfo: "skip", showlegend: false,
    // dot colour follows the cell: white on dark cells, black on light ones
    textfont: { size: mx.starts.length > 14 ? 7 : 9, color: z.flat().map((v) => v !== null && Math.abs(v) / lim > 0.55 ? "#ffffff" : "#111111") },
  }, {
    type: "scatter", mode: "markers", x: [a.start], y: [a.end], marker: { symbol: "square-open", size: 14, color: dark() ? "#ffffff" : "#111", line: { width: 2 } }, hoverinfo: "skip", showlegend: false,
  }], layoutBase({ hovermode: "closest", xaxis: { title: { text: t("common.startYear") }, dtick: tk * mx.step, tickangle: 0 }, yaxis: { title: { text: t("common.endYear") }, dtick: tk * mx.step }, margin: { l: 50, r: 10, t: 6, b: 40 } }));
  const el = $("#matrix");
  el.removeAllListeners && el.removeAllListeners("plotly_click");
  el.on("plotly_click", (ev) => {
    const pt = ev.points[0]; if (!pt || pt.data.type !== "heatmap") return;
    state.start = +pt.x; state.end = +pt.y; syncControls(); refresh(false);
  });
  $("#matrixNote").textContent = t(mx.step > 1 ? "charts.matrixNoteWithStep" : "charts.matrixNote", { minYears: mx.min_len, step: mx.step });
}
function renderSeason(a) {
  const names = Array.from({ length: 12 }, (_, i) => monthLabel(i + 1, "narrow"));
  const unit = V().units.replace(/ \(.*\)/, "");
  plot("season", [{ x: names.map((n, i) => `${i + 1}`), y: a.seasonal_cycle, type: "bar", marker: { color: "#8aa4bf" } }],
    layoutBase({ xaxis: { tickvals: names.map((n, i) => `${i + 1}`), ticktext: names }, yaxis: { title: { text: unit, font: { size: 11 } } }, margin: { l: 50, r: 6, t: 4, b: 24 }, hovermode: "closest" }),
    (ev) => `<div class="thead">${monthLabel(+ev.points[0].x)}</div><b>${fmt(ev.points[0].y)}</b> ${unit}`);
}
function renderSource(a) {
  const p = a.provenance;
  $("#source").innerHTML = `<p><b>${p.product}</b><br>${p.provider} · <span class="tag">${p.kind}</span> ${p.resolution}</p>
    <p>${p.citation} <a href="${p.url}" target="_blank" rel="noopener">${t("common.link")}</a></p>
    <p class="hint">${th("common.licence", { license: p.license })}</p>
    <ul>${p.caveats.map((c) => `<li>${c}</li>`).join("")}</ul>`;
}

// ---------------------------------------------------------------- refresh
let seq = 0, lastAnalysis = null, lastAnalysisQuery = "", lastMapQuery = "";
function renderAnalysis(a) {
  renderAnswer(a); renderCard(a); renderChart(a); renderMatrix(a); renderSeason(a); renderSource(a);
}
async function refreshAnalysis() {
  const my = ++seq;
  const params = query(true);
  writeHash();
  $("#dlCsv").href = `/api/export.csv?${query(true)}`;
  $("#dlJson").href = `/api/export.json?${query(true)}`;
  answerLoading();
  try {
    const a = await api("analysis", params);
    if (my !== seq) return;
    lastAnalysis = a._raw || a; lastAnalysisQuery = params;
    renderAnalysis(a);
  } catch (e) {
    if (my !== seq) return;
    $("#answer").classList.remove("loading");
    $("#answerBody").innerHTML = `<p class="err">${th("errors.analysisFailed", { message: e.message })}</p>`;
    $("#card").innerHTML = `<p class="err">${th("errors.analysisFailed", { message: e.message })}</p>`;
  }
}
let mapSeq = 0;
async function refresh(regionChanged) {
  const my = ++mapSeq;
  const params = query(false);
  if (regionChanged) { drawRegion(); drawSelection(); }
  refreshAnalysis();
  try {
    const m = await api("map", params);
    if (my === mapSeq) { lastMapQuery = params; drawGrid(m); }
  } catch (e) { if (my === mapSeq) $("#mapSummary").innerHTML = `<span class="err">${th("errors.mapUnavailable", { message: e.message })}</span>`; }
}

// ---------------------------------------------------------------- false-alarm lab
let simSeed = 7, simSeq = 0, lastSimulation = null, lastSimulationBatch = null, spikeSeed = 12, spikeExample = null;
async function simOne() {
  const seq = ++simSeq;
  const yrs = +$("#simYears").value, phi = +$("#simPhi").value;
  $("#simYearsV").textContent = yrs; $("#simPhiV").textContent = phi;
  try {
    const s = await api("simulate", new URLSearchParams({ seed: simSeed, years: yrs, phi }));
    if (seq !== simSeq) return;
    lastSimulation = s;
    renderSimulation(s);
  } catch (e) {
    if (seq === simSeq) $("#simOut").textContent = t("lab.loadError");
  }
}
function renderSimulation(s) {
  plot("simChart", [
    { x: s.dates, y: s.values, type: "scatter", mode: "lines", name: t("lab.simulatedSeries"), line: { color: "#8aa4bf" } },
    { x: s.dates, y: s.fit, type: "scatter", mode: "lines", name: t("lab.fittedLine"), line: { color: "#d6604d", width: 2.5 } },
  ], layoutBase({ annotations: [{ text: t("lab.simulationLabel"), xref: "paper", yref: "paper", x: 0.01, y: 0.98, showarrow: false, font: { size: 13, color: dark() ? "#d4a72c" : "#8a5a00" } }] }));
  const yes = (p) => p < 0.05 ? `<span class="err">${t("lab.fooled")}</span>` : t("lab.notFooled");
  $("#simOut").innerHTML = `<div><span>${t("lab.fittedSlope")}</span><b>${fmt(s.slope)} ${t("common.perDecade")}</b>${t("lab.trueValue")}</div>
    <div><span>${t("lab.naiveTest")}</span><b>${pStr(s.naive_p)}</b>${yes(s.naive_p)}</div>
    <div data-tip="${t("lab.effectiveNHint", { effective: Math.round(s.n_eff), total: s.years * 12 })}"><span>${t("lab.correctedTest")}</span><b>${pStr(s.corrected_p)}</b>${yes(s.corrected_p)}</div>`;
}
async function simMany() {
  const yrs = +$("#simYears").value, phi = +$("#simPhi").value;
  $("#simMany").disabled = true;
  $("#simMultiOut").textContent = t("common.running");
  try {
    lastSimulationBatch = await api("simulate_many", new URLSearchParams({ runs: 200, years: yrs, phi }));
    renderSimulationBatch(lastSimulationBatch);
  } catch (e) { $("#simMultiOut").textContent = t("lab.loadError"); }
  finally { $("#simMany").disabled = false; }
}
function renderSimulationBatch(r) {
  const counts = [r.naive_significant, r.corrected_significant];
  const labels = [t("lab.naiveTest"), t("lab.correctedTest")];
  // Older servers return counts without the Wilson intervals.
  const intervals = [r.naive_interval, r.corrected_interval].map((limits, i) =>
    (limits || wilsonInterval(counts[i], r.runs)).map((p) => 100 * p));
  const pct = counts.map((count) => 100 * count / r.runs);
  const percent = (value) => I18N.number(value, { maximumFractionDigits: 1 }) + "%";
  const ranges = intervals.map(([low, high]) => `${percent(low)}–${percent(high)}`);
  $("#simMulti").hidden = $("#simMultiStats").hidden = false;
  const ink = getComputedStyle(document.body).color;
  plot("simMulti", [{
    type: "bar", x: labels, y: pct, marker: { color: ["#d6604d", dark() ? "#5ea8ff" : "#0b5cad"] },
    error_y: { type: "data", symmetric: false, color: ink, array: intervals.map(([, high], i) => high - pct[i]),
      arrayminus: intervals.map(([low], i) => pct[i] - low), visible: true },
    customdata: counts.map((count, i) => `${th("lab.fooledCount", { count, total: r.runs })}<br>${th("lab.batchInterval", { range: ranges[i] })}`),
  }, {
    type: "bar", x: [t("lab.batchReference")], y: [5], marker: { color: dark() ? "#9aa7b4" : "#5f6c7a" },
    text: [percent(5)], textposition: "outside", customdata: [t("lab.honestTest")],
  }], layoutBase({ yaxis: { title: { text: t("lab.fooledAxis"), font: { size: 12 } }, ticksuffix: "%",
    range: [0, Math.min(100, Math.max(15, ...intervals.map(([, high]) => high + 8)))] },
    margin: { t: 16, b: 35 }, barmode: "overlay", hovermode: "closest", showlegend: false }));
  $("#simMultiStats").innerHTML = labels.map((label, i) => `<div><span>${label}</span><b>${percent(pct[i])}</b>` +
    `${th("lab.fooledCount", { count: counts[i], total: r.runs })}<br>${th("lab.batchInterval", { range: ranges[i] })}</div>`).join("");
  $("#simMultiOut").textContent = t("lab.batchSummary", { runs: r.runs, years: r.years, memory: I18N.number(r.phi) });
}
function wilsonInterval(count, runs) {
  const p = count / runs, z = 1.959963984540054, z2 = z * z;
  const denominator = 1 + z2 / runs;
  const center = (p + z2 / (2 * runs)) / denominator;
  const margin = z * Math.sqrt((p * (1 - p) + z2 / (4 * runs)) / runs) / denominator;
  return [Math.max(0, center - margin), Math.min(1, center + margin)];
}
async function loadSpikeExample() {
  const newButton = $("#simSpikeNew"), compare = $("#simSpikeCompare");
  if (newButton.disabled) return;
  newButton.disabled = compare.disabled = true;
  $("#simSpikeOut").textContent = t("common.running");
  try {
    const s = await api("simulate", new URLSearchParams({ seed: spikeSeed, years: 10, phi: 0.25, sigma: 0.35 }));
    spikeExample = addSpikes(s);
    renderSpikeExample();
  } catch (e) { $("#simSpikeOut").textContent = t("lab.loadError"); }
  finally {
    newButton.disabled = false;
    compare.disabled = !spikeExample;
  }
}
function addSpikes(s) {
  const n = s.values.length, center = (n - 1) / 2;
  const spikes = [Math.floor(n * 0.84), Math.floor(n * 0.95)];
  const heights = [8 * s.sigma, 10 * s.sigma];
  const values = s.values.slice();
  spikes.forEach((month, i) => { values[month] += heights[i]; });
  // On equally spaced months, OLS is linear in the values. Add the two spikes' contribution to the original fit.
  const sumSquares = s.values.reduce((sum, _, month) => sum + (month - center) ** 2, 0);
  const slopeChange = spikes.reduce((sum, month, i) => sum + (month - center) * heights[i], 0) / sumSquares;
  const meanChange = (heights[0] + heights[1]) / n;
  return { original: s, spikes, values, slope: s.slope + 120 * slopeChange, fit: s.fit.map((value, month) =>
    value + meanChange + (month - center) * slopeChange) };
}
function renderSpikeExample() {
  const s = spikeExample, compare = pressed($("#simSpikeCompare"));
  const dates = s.original.dates.map((month) => month + "-15");
  const withSpikes = t("lab.spikeWith"), withoutSpikes = t("lab.spikeWithout");
  const traces = [
    { x: dates, y: s.values, name: t("lab.syntheticValues"), type: "scatter", mode: "lines", line: { color: "#8095ad", width: 1.2 } },
    { x: dates, y: s.fit, name: withSpikes, type: "scatter", mode: "lines", line: { color: "#d6604d", width: 2.5 } },
    { x: s.spikes.map((i) => dates[i]), y: s.spikes.map((i) => s.values[i]), name: t("lab.spikePoints"),
      type: "scatter", mode: "markers", marker: { color: "#d6604d", size: 10, symbol: "diamond" } },
  ];
  if (compare) {
    const blue = dark() ? "#5ea8ff" : "#0b5cad";
    traces.push(
      { x: dates, y: s.original.fit, name: withoutSpikes, type: "scatter", mode: "lines", line: { color: blue, width: 2.5, dash: "dash" } },
      { x: s.spikes.map((i) => dates[i]), y: s.spikes.map((i) => s.original.values[i]), name: t("lab.spikeOriginalPoints"),
        type: "scatter", mode: "markers", marker: { color: blue, size: 8, symbol: "circle-open" } },
    );
  }
  plot("simSpikeChart", traces, layoutBase({ yaxis: { title: { text: t("lab.syntheticUnits"), font: { size: 12 } } } }));
  $("#simSpikeNote").hidden = !compare;
  const stat = (label, slope) => `<div><span>${label}</span><b>${fmt(slope)} ${t("common.perDecade")}</b></div>`;
  $("#simSpikeOut").innerHTML = stat(withSpikes, s.slope) + (compare ? stat(withoutSpikes, s.original.slope) : "");
}

// ---------------------------------------------------------------- about
function renderAbout() {
  const rows = CAT.variables.map((v) => `<tr><td><b>${v.name}</b><br><span class="tag">${v.kind}</span></td><td>${v.product}<br>${v.provider}</td><td>${v.resolution}<br>${v.years[0]}–${v.years[1]}</td><td>${v.citation} <a href="${v.url}" target="_blank" rel="noopener">${t("common.link")}</a><br><i>${v.license}</i></td></tr>`).join("");
  $("#aboutBody").innerHTML = `<h2>${t("methods.toolTitle")}</h2>
    <p>${th("methods.toolDescriptionHtml")}</p>
    <h2>${t("methods.dataTitle")}</h2><table><tr><th>${t("methods.variableColumn")}</th><th>${t("methods.productColumn")}</th><th>${t("methods.gridYearsColumn")}</th><th>${t("methods.citationLicenceColumn")}</th></tr>${rows}</table>
    <h2>${t("methods.methodsTitle")}</h2><ul>${Object.entries(CAT.methods).map(([k, v]) => `<li><b>${t(`methods.notes.${k}.label`)}:</b> ${esc(v)}</li>`).join("")}</ul>
    <p>${t("methods.references")}</p>
    <h2>${t("methods.limitsTitle")}</h2><p>${t("methods.limitsDescription")}</p>
    ${CAT.ai_disclosure ? `<h2>${t("methods.existingNoteTitle")}</h2><p>${esc(I18N.text(CAT.ai_disclosure))}</p>` : ""}`;
}

// ---------------------------------------------------------------- boot
(async function boot() {
  await I18N.init();
  readHash();
  setHeaderHeight(); window.addEventListener("resize", setHeaderHeight);
  watchCharts(); wireTips(); initLogoSpark();
  CAT = await api("catalog", "");
  if (!CAT.variables.some((v) => v.id === state.var)) state.var = "ndvi";
  if (!available(state.var, state.region)) {
    const v = CAT.variables.find((x) => Object.keys(CAT.available).some((k) => k.startsWith(x.id + "/") && CAT.available[k]));
    if (v) { state.var = v.id; state.region = v.regions.find((r) => available(v.id, r)); }
  }
  buildVarCards(); initMap(); wireControls(); syncControls(); renderAbout();
  $("#simNew").onclick = () => { simSeed = Math.floor(Math.random() * 1e6); simOne(); };
  $("#simYears").oninput = simOne; $("#simPhi").oninput = simOne;
  $("#simMany").onclick = simMany;
  $("#simSpikeNew").onclick = () => { spikeSeed += 1; loadSpikeExample(); };
  $("#simSpikeCompare").onclick = (e) => { setPressed(e.currentTarget, !pressed(e.currentTarget)); renderSpikeExample(); };
  if (window.initGlobeTab) window.initGlobeTab();
  window.addEventListener("languagechange", () => {
    hideTip();
    CAT = I18N.response("catalog", CAT._raw || CAT);
    buildVarCards(); syncControls(); renderAbout();
    // Map controls are owned by Leaflet and are outside the static text bindings.
    $(".leaflet-control-zoom-in").title = t("mapControls.zoomIn");
    $(".leaflet-control-zoom-out").title = t("mapControls.zoomOut");
    $(".leaflet-control-zoom-in").setAttribute("aria-label", t("mapControls.zoomIn"));
    $(".leaflet-control-zoom-out").setAttribute("aria-label", t("mapControls.zoomOut"));
    map.attributionControl.removeAttribution(baseLayer.options.attribution);
    baseLayer.options.attribution = t("detective.basemapAttribution", { source: '<a href="https://earthdata.nasa.gov/gibs" target="_blank" rel="noopener">NASA GIBS</a>' });
    map.attributionControl.addAttribution(baseLayer.options.attribution);
    $("#drawBtn span").textContent = t("common.selectArea");
    $("#drawBtn").dataset.tiphtml = t("detective.selectAreaTooltipHtml");
    $("#resetSel").setAttribute("aria-label", t("detective.wholeRegion"));
    $("#resetSel").dataset.tip = t("detective.resetSelectionHint");
    $(".drawbanner span").textContent = t("detective.dragToSelect");
    $(".drawbanner button").textContent = t("common.cancel");
    setHeaderHeight();
    // Reuse the source results, including charts in inactive tabs, without navigation or recomputation.
    if (lastAnalysis && lastAnalysisQuery === query(true)) renderAnalysis(I18N.response("analysis", lastAnalysis));
    if (lastMap && lastMapQuery === query(false)) drawGrid(I18N.response("map", lastMap._raw || lastMap));
    if (window.localiseGlobe) window.localiseGlobe();
    if (lastSimulation) renderSimulation(lastSimulation);
    if (lastSimulationBatch) renderSimulationBatch(lastSimulationBatch);
    if (spikeExample) renderSpikeExample();
    window.dispatchEvent(new Event("resize"));
  });
  await refresh(true);
})();
