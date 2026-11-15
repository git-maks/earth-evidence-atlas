/* Earth Evidence Atlas – 3D globe explorer (MapLibre GL globe + NASA GIBS).
 * Uses globals from app.js: CAT, CMAPS, colorAt, fmt, fmtP, api, layoutBase, plotCfg, state, $, $$. */
"use strict";

const G = {
  map: null, var: "gistemp", mode: "trend", year: null, months: ALL, imagery: "bluemarble", imgMonth: 7,
  place: "world", places: [], layers: [], monthly: null,
  grids: [], sel: null, playing: null, frameCache: new Map(), drawing: false, spin: true, opacity: 0.8,
};
const GLOBE_ZOOM = 1.5;
// whole globe in view on small screens: the globe is 512 * 2^zoom / pi px wide, so fit it into ~88% of the shorter side
function globeZoom() {
  const el = document.getElementById("globeMap"), side = Math.min(el.clientWidth || innerWidth, el.clientHeight || innerHeight);
  return Math.min(GLOBE_ZOOM, Math.log2((side * 0.88 * Math.PI) / 512));
}
const GIBS_BASE = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/";
const IMAGERY = {
  bluemarble: { layer: "BlueMarble_ShadedRelief_Bathymetry", ext: "jpeg", level: 8, time: null },
  truecolor: { layer: "MODIS_Terra_CorrectedReflectance_TrueColor", ext: "jpg", level: 9, time: "day", from: 2000 },
  ndvi: { layer: "MODIS_Terra_L3_NDVI_Monthly", legend: "MODIS_L3_NDVI", ext: "png", level: 7, time: "month", from: 2000 },
  lst: { layer: "MODIS_Terra_L3_Land_Surface_Temp_Monthly_Day", legend: "MODIS_Land_Surface_Temp", ext: "png", level: 6, time: "month", from: 2000 },
  merra: { layer: "MERRA2_2m_Air_Temperature_Monthly", ext: "png", level: 6, time: "month", from: 1980 },
  imerg: { layer: "IMERG_Precipitation_Rate", ext: "png", level: 6, time: "day", from: 2000 },
};
// World uses the latest published NASA visualization when the analysis cubes cover only places.
const WORLD_MONTHLY = {
  ndvi: IMAGERY.ndvi,
  lst_day: IMAGERY.lst,
  lst_day_aqua: { layer: "MODIS_Aqua_L3_Land_Surface_Temp_Monthly_Day", legend: "MODIS_Land_Surface_Temp", ext: "png", level: 6 },
  t2m: IMAGERY.merra,
  precip: { layer: "MERRA2_Precipitation_Bias_Corrected_Monthly", ext: "png", level: 6 },
  soil_root: { layer: "MERRA2_Soil_Water_Root_Zone_Monthly", ext: "png", level: 6 },
};

// ---------------------------------------------------------------- polar caps
// MapLibre's globe stretches the top/bottom pixel row of raster tiles over the poles (> 85.05°), which shows
// as a streaky disc. Two synthetic raster layers fade towards 85° into a horizontally blurred copy of the
// imagery's own edge colours, so the cap keeps the natural colours of the picture, only softened.
const POLAR = { from: 77, fromOver: 81, edge: 84.6, ver: 0, tpl: [], edges: new Map(), blank: null };
function tileLat(z, y, row) { // latitude of a pixel row inside an XYZ tile
  const n = Math.PI * (1 - 2 * (y * 256 + row) / (256 * 2 ** z));
  return (Math.atan(Math.sinh(n)) * 180) / Math.PI;
}
async function loadTileBand(url, north) {
  // average colour of the 24 pixel rows closest to the pole, per column (premultiplied by alpha)
  try {
    const r = await fetch(url);
    if (!r.ok) return null;
    const bmp = await createImageBitmap(await r.blob());
    const cv = document.createElement("canvas"); cv.width = 256; cv.height = 24;
    cv.getContext("2d").drawImage(bmp, 0, north ? 0 : -(bmp.height - 24) * 256 / bmp.height, 256, 256);
    const d = cv.getContext("2d").getImageData(0, 0, 256, 24).data, out = new Float32Array(256 * 4);
    for (let c = 0; c < 256; c++) for (let rr = 0; rr < 24; rr++) {
      const k = (rr * 256 + c) * 4, a = d[k + 3] / 255;
      out[c * 4] += d[k] * a / 24; out[c * 4 + 1] += d[k + 1] * a / 24; out[c * 4 + 2] += d[k + 2] * a / 24; out[c * 4 + 3] += a / 24;
    }
    return out;
  } catch (e) { return null; }
}
async function polarEdge(ver, z, x, north) {
  // blurred edge colours for one tile column, using its two neighbours so tile seams do not show
  const key = `${ver}|${z}|${x}|${north}`;
  if (!POLAR.edges.has(key)) POLAR.edges.set(key, (async () => {
    const n = 2 ** z, yy = north ? 0 : n - 1, tpl = POLAR.tpl[ver];
    const bands = await Promise.all([-1, 0, 1].map((dx) => loadTileBand(tpl.replace("{z}", z).replace("{x}", ((x + dx) % n + n) % n).replace("{y}", yy), north)));
    const W = 768, strip = new Float32Array(W * 4);
    bands.forEach((bd, i) => { if (bd) strip.set(bd, i * 1024); });
    const R = 56, out = new Float32Array(256 * 4);
    for (let c = 0; c < 256; c++) {
      const cc = c + 256; let acc = [0, 0, 0, 0], cnt = 0;
      for (let j = cc - R; j <= cc + R; j++) { const k = j * 4; acc[0] += strip[k]; acc[1] += strip[k + 1]; acc[2] += strip[k + 2]; acc[3] += strip[k + 3]; cnt++; }
      const a = acc[3] / cnt;
      out[c * 4] = a ? acc[0] / cnt / a : 0; out[c * 4 + 1] = a ? acc[1] / cnt / a : 0; out[c * 4 + 2] = a ? acc[2] / cnt / a : 0; out[c * 4 + 3] = a;
    }
    return out;
  })());
  return POLAR.edges.get(key);
}
async function polarMean(ver, north) {
  // one average colour for the whole polar edge (from the single world tile), so the very top has no streaks
  const key = `${ver}|mean|${north}`;
  if (!POLAR.edges.has(key)) POLAR.edges.set(key, (async () => {
    const bd = await loadTileBand(POLAR.tpl[ver].replace("{z}", 0).replace("{x}", 0).replace("{y}", 0), north);
    if (!bd) return null;
    let r = 0, g = 0, b = 0, a = 0;
    for (let c = 0; c < 256; c++) { r += bd[c * 4]; g += bd[c * 4 + 1]; b += bd[c * 4 + 2]; a += bd[c * 4 + 3]; }
    return a ? [r / a, g / a, b / a, a / 256] : null;
  })());
  return POLAR.edges.get(key);
}
async function polarTile(kind, ver, z, x, y) {
  const from = kind === "over" ? POLAR.fromOver : POLAR.from;
  const top = tileLat(z, y, 0), bot = tileLat(z, y, 256);
  const cv = document.createElement("canvas"); cv.width = cv.height = 256;
  const toBuf = () => new Promise((res) => cv.toBlob((b) => b.arrayBuffer().then(res), "image/png"));
  if (Math.max(Math.abs(top), Math.abs(bot)) < from && Math.sign(top) === Math.sign(bot)) {
    if (!POLAR.blank) POLAR.blank = await toBuf();
    return POLAR.blank.slice(0);
  }
  const north = top > 0, edge = await polarEdge(ver, z, x, north), mean = await polarMean(ver, north);
  const ctx = cv.getContext("2d"), img = ctx.createImageData(256, 256);
  for (let r = 0; r < 256; r++) {
    const la = Math.abs(tileLat(z, y, r + 0.5));
    let t = Math.max(0, Math.min(1, (la - from) / (POLAR.edge - from)));
    t = t * t * (3 - 2 * t);
    if (t <= 0) continue;
    // closer to the pole the colour slides from the local (blurred) edge colour to the polar mean
    const m = mean ? Math.pow(Math.max(0, (la - (POLAR.edge - 3)) / 3), 1.5) : 0, mm = Math.min(1, m);
    for (let c = 0; c < 256; c++) {
      const k = (r * 256 + c) * 4, e = c * 4;
      img.data[k] = edge[e] + (mm ? (mean[0] - edge[e]) * mm : 0);
      img.data[k + 1] = edge[e + 1] + (mm ? (mean[1] - edge[e + 1]) * mm : 0);
      img.data[k + 2] = edge[e + 2] + (mm ? (mean[2] - edge[e + 2]) * mm : 0);
      img.data[k + 3] = Math.round(255 * t * (edge[e + 3] + (mm ? (mean[3] - edge[e + 3]) * mm : 0)));
    }
  }
  ctx.putImageData(img, 0, 0);
  return toBuf();
}
maplibregl.addProtocol("polar", async (params) => {
  // polar://under|over/<imagery version>/z/x/y
  const [kind, ver, z, x, y] = params.url.replace("polar://", "").split("/");
  return { data: await polarTile(kind, +ver, +z, +x, +y) };
});
function polarTiles(kind) { return [`polar://${kind}/${POLAR.ver}/{z}/{x}/{y}`]; }
function setPolarImagery(tpl) {
  // called whenever the base imagery changes: the cap follows the new picture
  POLAR.ver = POLAR.tpl.length; POLAR.tpl.push(tpl);
  if (G.map && G.map.getSource("polar")) { G.map.getSource("polar").setTiles(polarTiles("under")); G.map.getSource("polar2").setTiles(polarTiles("over")); }
}

// ---------------------------------------------------------------- star field
// Real stars (Yale Bright Star Catalogue) drawn behind the globe for the direction the camera is looking:
// the sky behind the globe is the one seen from the planet's far side at the current sidereal time.
const STARS = { list: null, cv: null };
function gmstDeg(date) {
  const jd = date.getTime() / 86400000 + 2440587.5;
  return (280.46061837 + 360.98564736629 * (jd - 2451545.0)) % 360;
}
function starColour(bv) {
  if (bv < 0) return "170,191,255"; if (bv < 0.3) return "202,215,255"; if (bv < 0.6) return "248,247,255";
  if (bv < 0.9) return "255,244,234"; if (bv < 1.3) return "255,222,180"; return "255,200,150";
}
async function initStars() {
  STARS.cv = $("#gStars");
  try { STARS.list = (await (await fetch("/static/vendor/stars.json")).json()).stars; } catch (e) { STARS.list = []; }
  drawStars();
}
function drawStars() {
  const cv = STARS.cv, map = G.map;
  if (!cv || !STARS.list || !map) return;
  const W = cv.clientWidth, H = cv.clientHeight, dpr = window.devicePixelRatio || 1;
  if (cv.width !== Math.round(W * dpr) || cv.height !== Math.round(H * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const g = ctx.createRadialGradient(W * 0.5, H * 0.5, 0, W * 0.5, H * 0.5, Math.max(W, H) * 0.75);
  g.addColorStop(0, "#070d1c"); g.addColorStop(1, "#010208");
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  const rad = Math.PI / 180, c = map.getCenter(), gm = gmstDeg(new Date());
  // celestial (equatorial) unit vectors; the camera looks from above the map centre towards the Earth's centre
  const vec = (ra, dec) => [Math.cos(dec) * Math.cos(ra), Math.cos(dec) * Math.sin(ra), Math.sin(dec)];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const add = (a, b, ka, kb) => [a[0] * ka + b[0] * kb, a[1] * ka + b[1] * kb, a[2] * ka + b[2] * kb];
  const norm = (a) => { const l = Math.hypot(...a) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };
  let f = vec((c.lng + gm + 180) * rad, -c.lat * rad); // forward
  let up = norm(add([0, 0, 1], f, 1, -f[2]));
  if (!isFinite(up[0]) || Math.hypot(...up) < 0.5) up = [1, 0, 0];
  let right = cross(f, up);
  const b = map.getBearing() * rad, p = map.getPitch() * rad;
  [up, right] = [add(up, right, Math.cos(b), Math.sin(b)), add(right, up, Math.cos(b), -Math.sin(b))];
  [f, up] = [add(f, up, Math.cos(p), Math.sin(p)), add(up, f, Math.cos(p), -Math.sin(p))];
  const fov = ((map.transform && map.transform.fov) || 36.87) * rad;
  const fpx = (H / 2) / Math.tan(fov / 2), cx = W / 2, cy = H / 2;
  for (const [ra, dec, mag, bv] of STARS.list) {
    const s = vec(ra * rad, dec * rad), z = dot(s, f);
    if (z <= 0.05) continue;
    const x = cx + (dot(s, right) / z) * fpx, y = cy - (dot(s, up) / z) * fpx;
    if (x < -4 || y < -4 || x > W + 4 || y > H + 4) continue;
    const r = Math.max(0.5, 2.4 - 0.33 * mag), a = Math.max(0.35, Math.min(1, 1.35 - mag * 0.14));
    ctx.fillStyle = `rgba(${starColour(bv)},${a.toFixed(2)})`;
    ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI); ctx.fill();
    if (mag < 1.2) { ctx.fillStyle = `rgba(${starColour(bv)},0.12)`; ctx.beginPath(); ctx.arc(x, y, r * 3, 0, 2 * Math.PI); ctx.fill(); }
  }
}

// ---------------------------------------------------------------- helpers
const MERC_LIM = 85.05;
const mercY = (lat) => Math.log(Math.tan(Math.PI / 4 + (Math.max(-MERC_LIM, Math.min(MERC_LIM, lat)) * Math.PI) / 360));
const latFromY = (y) => (Math.atan(Math.exp(y)) * 360) / Math.PI - 90;
function GV() { return CAT.variables.find((v) => v.id === G.var); }
function rectPoly(b, n = 24) { // densified rectangle so edges follow parallels on the globe
  const [w, s, e, nn] = b, pts = [];
  for (let i = 0; i <= n; i++) pts.push([w + (e - w) * i / n, nn]);
  for (let i = 0; i <= n; i++) pts.push([e, nn - (nn - s) * i / n]);
  for (let i = 0; i <= n; i++) pts.push([e - (e - w) * i / n, s]);
  for (let i = 0; i <= n; i++) pts.push([w, s + (nn - s) * i / n]);
  return { type: "Feature", geometry: { type: "Polygon", coordinates: [pts] }, properties: {} };
}
function cellSize(arr) { return arr.length > 1 ? Math.abs(arr[1] - arr[0]) : 2; }
function gridBounds(lat, lon, clip = [-180, -90, 180, 90]) {
  const dl = cellSize(lat), dn = cellSize(lon);
  return [Math.max(clip[0], Math.min(...lon) - dn / 2), Math.max(clip[1], -MERC_LIM, Math.min(...lat) - dl / 2),
    Math.min(clip[2], Math.max(...lon) + dn / 2), Math.min(clip[3], MERC_LIM, Math.max(...lat) + dl / 2)];
}
function gridImage(lat, lon, values, colorFn, bounds = gridBounds(lat, lon)) {
  // values[i][j] on a regular lat/lon grid -> canvas in Web-Mercator rows (MapLibre stretches images linearly in Mercator)
  const [w, s, e, n] = bounds;
  const nx = lon.length, ny = lat.length, dl = cellSize(lat), dn = cellSize(lon);
  const W = Math.min(1024, Math.max(nx, nx * Math.floor(512 / nx) || nx));
  const yN = mercY(n), yS = mercY(s);
  const H = Math.min(1024, Math.max(ny, Math.round(W * (yN - yS) / ((e - w) * Math.PI / 180))));
  const cv = document.createElement("canvas"); cv.width = W; cv.height = H;
  const ctx = cv.getContext("2d"), img = ctx.createImageData(W, H);
  const lat0 = Math.min(...lat), lon0 = Math.min(...lon);
  const colCache = new Map();
  for (let r = 0; r < H; r++) {
    const la = latFromY(yN - (yN - yS) * (r + 0.5) / H);
    const i = Math.round((la - lat0) / dl);
    if (i < 0 || i >= ny) continue;
    for (let c = 0; c < W; c++) {
      const lo = w + (e - w) * (c + 0.5) / W, j = Math.round((lo - lon0) / dn);
      if (j < 0 || j >= nx) continue;
      const v = values[i][j];
      let rgba = colCache.get(v);
      if (rgba === undefined) { rgba = colorFn(v); colCache.set(v, rgba); }
      if (!rgba) continue;
      const k = (r * W + c) * 4; img.data[k] = rgba[0]; img.data[k + 1] = rgba[1]; img.data[k + 2] = rgba[2]; img.data[k + 3] = rgba[3];
    }
  }
  ctx.putImageData(img, 0, 0);
  return { url: cv.toDataURL(), coords: [[w, n], [e, n], [e, s], [w, s]] };
}
function rgbaOf(stops, x, a = 230) {
  const m = colorAt(stops, x).match(/\d+/g).map(Number);
  return [m[0], m[1], m[2], a];
}

// ---------------------------------------------------------------- map
function gibsTiles(key) {
  const L = IMAGERY[key];
  let t = "";
  if (L.time) {
    const y = G.year || 2020, m = String(G.imgMonth).padStart(2, "0");
    t = (L.time === "month" ? `${y}-${m}-01` : `${y}-${m}-15`) + "/";
  } else t = "";
  return [gibsTileTemplate(L, t)];
}
function gibsTileTemplate(layer, date) {
  return `${GIBS_BASE}${layer.layer}/default/${date}GoogleMapsCompatible_Level${layer.level}/{z}/{y}/{x}.${layer.ext}`;
}
function initGlobe() {
  G.map = new maplibregl.Map({
    container: "globeMap",
    style: {
      version: 8,
      projection: { type: "globe" },
      sources: {
        base0: { type: "raster", tiles: gibsTiles("bluemarble"), tileSize: 256, maxzoom: 8 },
        base1: { type: "raster", tiles: gibsTiles("bluemarble"), tileSize: 256, maxzoom: 8 },
        polar: { type: "raster", tiles: (setPolarImagery(gibsTiles("bluemarble")[0]), polarTiles("under")), tileSize: 256, maxzoom: 4 },
        polar2: { type: "raster", tiles: polarTiles("over"), tileSize: 256, maxzoom: 4 },
      },
      layers: [
        { id: "space", type: "background", paint: { "background-color": "#0b1a2e" } },
        // two base layers so a new date can load underneath and cross-fade without a black flash
        { id: "base1", type: "raster", source: "base1", paint: { "raster-opacity": 0, "raster-opacity-transition": { duration: 450 }, "raster-fade-duration": 0 } },
        { id: "base0", type: "raster", source: "base0", paint: { "raster-opacity": 1, "raster-opacity-transition": { duration: 450 }, "raster-fade-duration": 0 } },
        { id: "polar", type: "raster", source: "polar", paint: { "raster-fade-duration": 0 } },
      ],
      sky: { "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 5, 1, 7, 0] },
    },
    center: [20, 25], zoom: globeZoom(), maxZoom: 10,
    locale: {
      "Map.Title": t("mapControls.dragPan"),
      "NavigationControl.ZoomIn": t("mapControls.zoomIn"),
      "NavigationControl.ZoomOut": t("mapControls.zoomOut"),
      "NavigationControl.ResetBearing": t("mapControls.resetBearing"),
      "AttributionControl.ToggleAttribution": t("mapControls.attributionToggle"),
    },
    attributionControl: false,
  });
  G.navigation = new maplibregl.NavigationControl({ visualizePitch: true });
  G.map.addControl(G.navigation, "top-right");
  localiseGlobeCredits();
  baseKey = gibsTiles("bluemarble")[0];
  G.map.on("move", drawStars);
  G.map.on("resize", drawStars);
  initStars();
  G.map.on("load", async () => {
    try {
      const topo = await (await fetch("/static/vendor/countries-110m.json")).json();
      G.map.addSource("borders", { type: "geojson", data: topojson.mesh(topo, topo.objects.countries) });
    } catch (e) { G.map.addSource("borders", { type: "geojson", data: { type: "FeatureCollection", features: [] } }); }
    G.map.addLayer({ id: "polar2", type: "raster", source: "polar2", paint: { "raster-fade-duration": 0 } });
    G.map.addLayer({ id: "borders", type: "line", source: "borders", paint: { "line-color": "#ffffff", "line-opacity": 0.45, "line-width": 0.7 } });
    G.map.addSource("regions", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    G.map.addLayer({ id: "regions", type: "line", source: "regions", paint: { "line-color": "#7cc4ff", "line-width": 1.5, "line-dasharray": [2, 2] } });
    G.map.addSource("similar", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    G.map.addLayer({ id: "similar-fill", type: "fill", source: "similar", paint: {
      "fill-color": "#4ad9dd", "fill-opacity": ["case", ["get", "active"], 0.34, 0.18],
    } });
    G.map.addLayer({ id: "similar-outline", type: "line", source: "similar", paint: { "line-color": "#091923", "line-width": 5 } });
    G.map.addLayer({ id: "similar-line", type: "line", source: "similar", paint: {
      "line-color": ["case", ["get", "active"], "#e5ffff", "#4ad9dd"], "line-width": 2.5,
    } });
    G.map.addSource("sel", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    G.map.addLayer({ id: "sel-fill", type: "fill", source: "sel", paint: { "fill-color": "#ffd166", "fill-opacity": 0.12 } });
    G.map.addLayer({ id: "sel", type: "line", source: "sel", paint: { "line-color": "#ffd166", "line-width": 2.5 } });
    $("#gWorld").disabled = false;
    await loadLayers();
    spin();
  });
  // slow rotation until the operator touches the globe
  ["mousedown", "touchstart", "wheel", "dragstart"].forEach((ev) => G.map.on(ev, () => { G.spin = false; }));
  G.map.on("moveend", () => spin());
  G.map.on("mousemove", hover);
  G.map.on("mouseout", hideTip);
  G.map.on("click", (e) => {
    if (G.drawing) return;
    const [match] = G.map.getLayer("similar-fill") ? G.map.queryRenderedFeatures(e.point, { layers: ["similar-fill"] }) : [];
    if (match) focusSimilarArea(+match.properties.index);
    else clickCell(e.lngLat);
  });
  // rectangle drawing
  let start = null;
  G.map.on("mousedown", (e) => { if (!G.drawing) return; e.preventDefault(); start = e.lngLat; });
  G.map.on("mousemove", (e) => {
    if (!G.drawing || !start) return;
    setSelection(normBox(start, e.lngLat), false);
  });
  G.map.on("mouseup", (e) => {
    if (!G.drawing || !start) return;
    const b = normBox(start, e.lngLat); start = null; setDrawing(false);
    if (b[2] - b[0] < 0.2 || b[3] - b[1] < 0.2) return;
    setSelection(b, true);
  });
  // the same rectangle with one finger
  let last = null;
  G.map.on("touchstart", (e) => {
    if (!G.drawing || e.points.length !== 1) return;
    e.preventDefault(); start = last = e.lngLat;
  });
  G.map.on("touchmove", (e) => {
    if (!G.drawing || !start) return;
    e.preventDefault(); last = e.lngLat; setSelection(normBox(start, last), false);
  });
  G.map.on("touchend", () => {
    if (!G.drawing || !start) return;
    const b = normBox(start, last); start = null; setDrawing(false);
    if (b[2] - b[0] < 0.2 || b[3] - b[1] < 0.2) { setSelection(null, false); return; }
    setSelection(b, true);
  });
}
function spin() {
  if (!G.spin || !G.map || !$("#globe").classList.contains("active") || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const c = G.map.getCenter(); c.lng -= 6;
  G.map.easeTo({ center: c, duration: 2000, easing: (t) => t });
}
function normBox(a, b) {
  return [Math.min(a.lng, b.lng), Math.min(a.lat, b.lat), Math.max(a.lng, b.lng), Math.max(a.lat, b.lat)].map((x) => +x.toFixed(2));
}
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && G.drawing) setDrawing(false); });
function setDrawing(on) {
  G.drawing = on; G.spin = false;
  if (on) G.map.stop(); // a running spin would move the globe under the finger while drawing
  $("#gDraw").classList.toggle("on", on);
  G.map.getCanvas().style.cursor = on ? "crosshair" : "";
  $("#globeMap").classList.toggle("drawing", on); // touch-action: none, so a finger draws instead of scrolling the page
  on ? G.map.dragPan.disable() : G.map.dragPan.enable();
  $("#gDraw").lastChild.textContent = on ? t("globe.dragToSelect") : t("common.selectArea");
}

// ---------------------------------------------------------------- data layers
let layersSeq = 0;
const savedPlaces = () => lsGet("atlas.globePlaces", []);
const sameBox = (a, b) => a.every((coordinate, i) => coordinate === b[i]);
const coversPlace = ([w, s, e, n], [west, south, east, north]) => w <= west && s <= south && e >= east && n >= north;
function saveGlobePlace(variable, dataRegion, bbox) {
  const saved = savedPlaces();
  const existing = saved.find((place) => sameBox(place.bbox, bbox));
  const region = existing ? existing.region : `saved-${bbox.join(",")}`;
  const place = { region, dataRegion, variable, bbox, name: bbox.join(", "), custom: true };
  lsSet("atlas.globePlaces", [...saved.filter((l) => !sameBox(l.bbox, bbox)), place]);
}
function placesForDataset(layers, variable) {
  const visible = layers.filter((l) => AREAS.visible(l.region));
  const owned = AREAS.mine();
  const registered = CAT.regions.filter((r) => r.custom && owned.includes(r.id) && AREAS.visible(r.id))
    .map(({ id, name, bbox, custom }) => ({ region: id, name, bbox, custom }));
  const places = [...visible];
  for (const place of [...registered, ...savedPlaces()]) {
    if (places.some((l) => l.custom && sameBox(l.bbox, place.bbox))) continue;
    const original = place.variable === variable && layers.find((l) => l.region === place.dataRegion);
    const source = original || visible.find((l) => coversPlace(l.bbox, place.bbox));
    places.push({ ...place, dataRegion: source ? source.region : null });
  }
  return places;
}
async function loadLayers(cached) {
  if (!G.map || !G.map.getSource("regions")) return;
  const seq = ++layersSeq;
  const v = GV();
  let all;
  try {
    all = cached || await api("layers", new URLSearchParams({ var: v.id }));
  } catch (e) {
    if (seq === layersSeq) {
      $("#gPlaceNote").textContent = t("globe.coverageError");
      $("#gPlaceNote").hidden = false;
    }
    return;
  }
  if (seq !== layersSeq) return;
  G.allPlaces = all;
  G.allPlacesVar = v.id;
  G.places = placesForDataset(all, v.id);
  const regional = G.places.filter((l) => l.region !== "world");
  if (G.place !== "world" && !regional.some((l) => l.region === G.place) && (G.place !== "all" || !regional.length)) G.place = "world";
  const others = all.filter((l) => l.custom && !AREAS.mine().includes(l.region) && !AREAS.hidden().includes(l.region));
  $("#gOthersRow").hidden = !others.length && !AREAS.others();
  $("#gShowOthers").checked = AREAS.others();
  const short = (l) => t(`catalog.regions.${l.region}.shortName`);
  $$("#gRegions [data-r]:not(#gWorld)").forEach((b) => b.remove());
  $("#gRegions").insertAdjacentHTML("beforeend",
    (regional.length ? `<button class="chip" data-r="all" data-tip="${esc(t("globe.allPlacesHint"))}">${t("globe.allPlaces")}</button>` : "") +
    regional.map((l) => `<button class="chip" data-r="${l.region}" ${l.custom ? `data-tip="${esc(l.name)}"` : ""}>${l.custom ? ic("pin") : ""}${l.custom ? (l.region.startsWith("saved-") || AREAS.mine().includes(l.region) ? t("globe.myArea") : t("globe.area")) : short(l)}` +
      (l.custom ? `<span class="chipx" role="button" tabindex="0" aria-label="${esc(t("common.hideArea"))}" data-hide="${l.region}">${ic("close")}</span>` : "") + `</button>`).join(""));
  $$("#gRegions .chipx").forEach((x) => x.onclick = (ev) => {
    ev.stopPropagation(); hideTip();
    const id = x.dataset.hide;
    if (id.startsWith("saved-")) lsSet("atlas.globePlaces", savedPlaces().filter((l) => l.region !== id));
    else AREAS.hide(id);
    loadLayers();
    if (similar.opened) renderSimilarAreas();
    if (typeof syncControls === "function" && CAT) syncControls();
  });
  $$("#gRegions [data-r]:not(#gWorld)").forEach((b) => b.onclick = () => selectGlobePlace(b.dataset.r));
  const [y0, y1] = v.years;
  if (!G.year || G.year < y0 || G.year > y1) G.year = y1;
  $("#gYear").min = y0; $("#gYear").max = y1; $("#gYear").value = G.year; $("#gYearV").textContent = G.year;
  $("#gVarMeta").innerHTML = `<span class="tag">${v.kind}</span> ${y0}–${y1}`;
  $("#gVarInfo").dataset.tiphtml = `<b>${v.product}</b><br>${v.resolution}<br><span class="muted">${v.definition}</span>`;
  setImagery();
  await applyGlobePlace();
}
function selectGlobePlace(place) {
  G.place = place;
  G.spin = false;
  if (G.drawing) setDrawing(false);
  $("#gClose").click();
  hideTip();
  const region = G.places.find((l) => l.region === place);
  if (place === "world" || place === "all") {
    G.map.easeTo({ zoom: globeZoom(), pitch: 0, bearing: 0, duration: 900 });
  } else if (region) {
    const [w, s, e, n] = region.bbox;
    G.map.fitBounds([[w, Math.max(s, -70)], [e, Math.min(n, 75)]], { padding: 60, duration: 1800 });
    if (region.custom) setSelection(region.bbox, true);
  }
  applyGlobePlace();
}
function applyGlobePlace() {
  const global = G.places.find((l) => l.region === "world");
  const regional = G.places.filter((l) => l.region !== "world");
  const place = G.place;
  G.monthly = place === "world" && !global ? WORLD_MONTHLY[G.var] : null;
  const shown = place === "all" || G.monthly ? regional : G.places.filter((l) => l.region === place);
  // In the combined view use the enclosing grid for nested areas.
  const withData = shown.filter((l) => l.dataRegion !== null);
  G.layers = withData.filter((l) => !withData.some((o) => coversPlace(o.bbox, l.bbox) && !sameBox(o.bbox, l.bbox)));
  G.map.getSource("regions").setData({ type: "FeatureCollection", features: shown.filter((l) => l.region !== "world").map((l) => rectPoly(l.bbox)) });
  $$("#gRegions [data-r]").forEach((b) => setPressed(b, b.dataset.r === place));
  const note = $("#gPlaceNote");
  note.textContent = t(shown.some((l) => l.dataRegion === null) ? "globe.noPlaceData" : "globe.noDatasetData");
  note.hidden = G.layers.length > 0 || Boolean(G.monthly);
  syncGlobeDisplay();
  return drawData();
}

// ---------------------------------------------------------------- similar areas
const similar = { opened: false, sequence: 0, status: "", result: null, active: -1, markers: [], grid: null };
function similarReference() {
  const a = G.lastAnalysis && G.lastAnalysis.raw;
  return a && a.variable === G.var && available(a.variable, "world") && Number.isFinite(a.result.slope) ? a : null;
}
function updateSimilarMap() {
  const source = G.map && G.map.getSource("similar");
  if (!source) return;
  const matches = similar.opened && similar.result ? similar.result.matches : [];
  source.setData({ type: "FeatureCollection", features: matches.map(({ bbox }, index) => ({
    ...rectPoly(bbox), properties: { index, active: index === similar.active },
  })) });
  similar.markers.forEach((marker, index) => marker.getElement().setAttribute("aria-pressed", index === similar.active));
}
function resetSimilarAreas() {
  similar.sequence++;
  Object.assign(similar, { opened: false, status: "", result: null, active: -1 });
  renderSimilarAreas();
}
function matchCenter([w, s, e, n]) { return [(w + e) / 2, (s + n) / 2]; }
function matchCoordinates(bbox) {
  const [lon, lat] = matchCenter(bbox);
  const degrees = (value) => I18N.number(Math.abs(value), { maximumFractionDigits: 1 }) + "°";
  return `${degrees(lat)} ${lat < 0 ? "S" : "N"}, ${degrees(lon)} ${lon < 0 ? "W" : "E"}`;
}
function focusSimilarArea(index) {
  const match = similar.result && similar.result.matches[index];
  if (!match) return;
  similar.active = index;
  $$("#gSimilarList [data-match]").forEach((button) => button.setAttribute("aria-pressed", +button.dataset.match === index));
  updateSimilarMap();
  const [w, s, e, n] = match.bbox;
  // The viewport uses Mercator coordinates at close zoom, while the match uses the full grid bounds.
  const south = Math.max(-MERC_LIM, Math.min(MERC_LIM - 0.1, s));
  const north = Math.min(MERC_LIM, Math.max(-MERC_LIM + 0.1, n));
  G.map.fitBounds([[w, south], [e, north]], { padding: 60, maxZoom: 5, duration: 900 });
  if (PHONE()) $("#globeMap").scrollIntoView({ block: "start", behavior: "smooth" });
}
function renderSimilarAreas() {
  const a = similarReference();
  const opened = Boolean(a && similar.opened), result = opened ? similar.result : null;
  $("#gSimilar").hidden = !a;
  $("#gSimilarOptions").hidden = !opened;
  $("#gSimilarToggle").setAttribute("aria-expanded", opened);
  $("#gSimilarGo").disabled = similar.status === "running";
  $("#gSimilarUnit").textContent = a ? GV().trend_units : "";
  $("#gSimilarStatus").textContent = result && result.matches.length ? t("similar.found", { count: result.matches.length }) :
    similar.status ? t(`similar.${similar.status}`) : "";
  const unit = a ? GV().trend_units : "";
  const trend = (value) => `${value > 0 ? "+" : ""}${fmt(value)} ${unit}`;
  $("#gSimilarReference").hidden = !result;
  $("#gSimilarReference").textContent = result ? t("similar.reference", { trend: trend(result.reference), cells: result.cells }) : "";
  const matches = result ? result.matches : [];
  const stored = savedPlaces().map((place) => place.bbox);
  const owned = AREAS.mine();
  if (CAT) stored.push(...CAT.regions.filter((region) => owned.includes(region.id) && AREAS.visible(region.id)).map((region) => region.bbox));
  $("#gSimilarList").innerHTML = matches.map(({ bbox, trend: value, difference }, i) => {
    const saved = stored.some((box) => sameBox(box, bbox));
    const details = t("similar.trendDifference", { trend: trend(value), difference: fmt(difference) });
    return `<li><button type="button" class="gmatch-area" data-match="${i}" aria-pressed="${i === similar.active}">` +
      `<span class="gmatch-num">${i + 1}</span><span>${matchCoordinates(bbox)}<small>${esc(details)}</small></span></button>` +
      `<button type="button" class="btn ghost small" data-save-match="${i}" ${saved ? "disabled" : ""}>${t(saved ? "similar.saved" : "similar.save")}</button></li>`;
  }).join("");
  similar.markers.forEach((marker) => marker.remove());
  similar.markers = matches.map(({ bbox }, i) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "gmatch-pin";
    button.textContent = i + 1;
    button.setAttribute("aria-label", t("similar.markerLabel", { rank: i + 1, coordinates: matchCoordinates(bbox) }));
    button.onclick = (event) => { event.stopPropagation(); focusSimilarArea(i); };
    return new maplibregl.Marker({ element: button, opacityWhenCovered: "0" }).setLngLat(matchCenter(bbox)).addTo(G.map);
  });
  updateSimilarMap();
}
async function searchSimilarAreas() {
  const a = similarReference();
  if (!a) return;
  const sequence = ++similar.sequence;
  const tolerance = $("#gSimilarTolerance").valueAsNumber, limit = $("#gSimilarLimit").valueAsNumber;
  Object.assign(similar, { status: "running", result: null, active: -1 });
  renderSimilarAreas();
  const query = new URLSearchParams({ var: a.variable, region: "world", start: a.start, end: a.end, months: a.months.join(",") });
  const key = query.toString();
  if (!similar.grid || similar.grid.key !== key) similar.grid = { key, request: api("map", query) };
  const grid = similar.grid;
  try {
    const data = await grid.request;
    if (sequence !== similar.sequence) return;
    similar.result = findSimilarWindows(data, a.bbox, tolerance, limit);
    similar.status = similar.result ? (similar.result.matches.length ? "" : "noMatches") : "noReference";
    if (similar.result && similar.result.matches.length) {
      G.spin = false;
      G.map.easeTo({ zoom: globeZoom(), pitch: 0, bearing: 0, duration: 700 });
    }
  } catch {
    if (similar.grid === grid) similar.grid = null;
    if (sequence !== similar.sequence) return;
    similar.status = "loadError";
  }
  renderSimilarAreas();
}
const imgCache = new Map();
async function fetchFrame(l, mode, year) {
  const key = `${mode}|${G.var}|${l.region}|${l.dataRegion || l.region}|${G.months}|${mode === "year" ? year : ""}`;
  if (!G.frameCache.has(key)) {
    const q = new URLSearchParams({ var: G.var, region: l.dataRegion || l.region, months: G.months, ...(mode === "year" ? { year } : {}) });
    const request = api(mode === "year" ? "frame" : "map", q).catch(() => {
      if (G.frameCache.get(key) === request) G.frameCache.delete(key);
      return null;
    });
    G.frameCache.set(key, request);
  }
  return [key, await G.frameCache.get(key)];
}
function prefetchYear(year) { G.layers.forEach((l) => fetchFrame(l, "year", year)); }
const monthlyChecks = new Map();
function checkMonthlyTiles(template) {
  if (!monthlyChecks.has(template)) {
    const sample = template.replace("{z}", 0).replace("{x}", 0).replace("{y}", 0);
    const check = fetch(sample, { signal: AbortSignal.timeout(6000) })
      .then((r) => r.ok && (r.headers.get("content-type") || "").startsWith("image/"))
      .catch(() => false);
    monthlyChecks.set(template, check);
  }
  return monthlyChecks.get(template);
}
let drawSeq = 0;
async function drawData() {
  if (!G.map || !G.map.getSource("regions")) return;
  const seq = ++drawSeq;
  const removeGrid = (id) => { if (G.map.getLayer(id)) G.map.removeLayer(id); if (G.map.getSource(id)) G.map.removeSource(id); };
  const show = $("#gShow").checked, monthly = show && G.monthly;
  const template = monthly && gibsTileTemplate(monthly, "default/");
  const monthlyId = "global-monthly";
  const source = G.map.getSource(monthlyId);
  if (source && source.serialize().tiles[0] !== template) removeGrid(monthlyId);
  const layers = show ? G.layers : [];
  const keepGrids = (regions) => {
    G.grids = G.grids.filter((g) => {
      if (regions.some((l) => l.region === g.region)) return true;
      removeGrid(g.id);
      return false;
    });
    if (!G.grids.length) $("#gLegend").innerHTML = "";
  };
  G.map.setLayoutProperty("regions", "visibility", G.monthly ? "none" : "visible");
  const note = $("#gPlaceNote");
  if (G.monthly) note.hidden = true;
  if (monthly) {
    keepGrids([]);
    if (!G.map.getSource(monthlyId)) {
      note.textContent = t("globe.loadingMonthlyLayer");
      note.hidden = false;
      const check = checkMonthlyTiles(template);
      const reachable = await check;
      if (!reachable && monthlyChecks.get(template) === check) monthlyChecks.delete(template);
      if (seq !== drawSeq) return;
      if (reachable) {
        G.map.addSource(monthlyId, { type: "raster", tiles: [template], tileSize: 256, maxzoom: monthly.level });
        G.map.addLayer({ id: monthlyId, type: "raster", source: monthlyId, paint: { "raster-opacity": G.opacity, "raster-fade-duration": 0 } }, "polar2");
      }
    }
    if (G.map.getSource(monthlyId)) {
      note.hidden = true;
      $("#gLegend").innerHTML = `<div class="lrow"><b>${t("globe.latestMonthlyLayer")}</b> · NASA GIBS</div><div class="lrow">${GV().name}</div>` +
        `<div class="lrow"><a href="https://gibs.earthdata.nasa.gov/legends/${monthly.legend || monthly.layer}_H.svg" target="_blank" rel="noopener">${t("globe.colourKey")}</a></div>`;
      return;
    }
    note.textContent = layers.length ? t("globe.gibsRegionalFallback") : t("globe.gibsUnavailable");
    G.map.setLayoutProperty("regions", "visibility", "visible");
  }
  keepGrids(layers);
  if (!layers.length) return;
  const v = GV(), stops = CMAPS[v.colormap] || CMAPS.RdBu_r, mode = G.mode, year = G.year;
  const data = await Promise.all(layers.map(async (l) => [l, ...(await fetchFrame(l, mode, year))]));
  if (seq !== drawSeq) return; // a newer frame was requested meanwhile
  const ok = data.filter(([, , d]) => d);
  const lim = Math.max(...ok.map(([, , d]) => d.color_limit || 0), 1e-9);
  const fade = pressed($("#gFade"));
  const grids = [];
  ok.forEach(([l, key, d]) => {
    const vals = mode === "year" ? d.values : d.slope;
    const sig = mode === "trend" ? d.sig_fdr : null;
    const bounds = gridBounds(d.lat, d.lon, l.bbox);
    if (bounds[0] >= bounds[2] || bounds[1] >= bounds[3]) return;
    const ik = `${key}|${lim}|${fade}`;
    let im = imgCache.get(ik);
    if (!im) {
      im = gridImage(d.lat, d.lon, vals.map((row, i) => row.map((x, j) => x === null ? null : (sig && !sig[i][j] ? "n" : "") + x)),
        (s) => {
          if (s === null) return [120, 120, 120, 70];
          const faint = typeof s === "string" && s[0] === "n";
          const x = parseFloat(faint ? s.slice(1) : s);
          return rgbaOf(stops, 0.5 + x / (2 * lim), faint && fade ? 70 : 230);
        }, bounds);
      if (imgCache.size > 400) imgCache.clear();
      imgCache.set(ik, im);
    }
    const id = `grid-${l.region}`, src = G.map.getSource(id);
    if (src && src.updateImage) {
      // swap the picture in place: the old frame stays on screen until the new one is decoded (no flicker)
      src.updateImage({ url: im.url, coordinates: im.coords });
    } else {
      G.map.addSource(id, { type: "image", url: im.url, coordinates: im.coords });
      G.map.addLayer({ id, type: "raster", source: id, paint: { "raster-opacity": G.opacity, "raster-resampling": "nearest", "raster-fade-duration": 0 } }, "polar2");
    }
    grids.push({ id, lat: d.lat, lon: d.lon, bounds, vals, p: d.p, sig, region: l.region, year });
  });
  G.grids.filter((g) => !grids.some((n) => n.id === g.id)).forEach((g) => removeGrid(g.id));
  G.grids = grids;
  if (!grids.length) { $("#gLegend").innerHTML = ""; return; }
  const grad = Array.from({ length: 11 }, (_, k) => colorAt(stops, k / 10)).join(",");
  const unit = mode === "year" ? t("globe.unitVsAverage", { unit: v.units.replace(/ \(.*\)/, "") }) : v.trend_units;
  $("#gLegend").innerHTML = `<div class="lrow"><b>${mode === "year" ? t("globe.annualComparison", { year }) : t("globe.trendPeriod", { start: v.years[0], end: v.years[1] })}</b> · ${v.name.replace(/ \(.*\)/, "")}</div>` +
    `<div class="lrow"><span>${fmt(-lim, 2)}</span><span class="bar" style="background:linear-gradient(90deg,${grad})"></span><span>+${fmt(lim, 2)} ${unit}</span></div>`;
}
function gridAt(ll) {
  for (const g of G.grids) {
    const [w, s, e, n] = g.bounds;
    if (ll.lng < w || ll.lng >= e || ll.lat < s || ll.lat >= n) continue;
    const dl = cellSize(g.lat), dn = cellSize(g.lon);
    const i = Math.round((ll.lat - Math.min(...g.lat)) / dl), j = Math.round((ll.lng - Math.min(...g.lon)) / dn);
    if (i >= 0 && i < g.lat.length && j >= 0 && j < g.lon.length) return { g, i, j, dl, dn };
  }
  return null;
}
function hover(e) {
  if (G.drawing) { hideTip(); return; }
  const h = gridAt(e.lngLat);
  if (!h) { hideTip(); return; }
  const v = GV(), x = h.g.vals[h.i][h.j];
  const html = x === null ? t("globe.tooFewData") :
    (!h.g.sig ? `<div class="thead">${h.g.year}</div><b>${x > 0 ? "+" : ""}${fmt(x)}</b> ${t("globe.unitVsAverage", { unit: v.units.replace(/ \(.*\)/, "") })}` :
      `<b>${x > 0 ? "+" : ""}${fmt(x)}</b> ${v.trend_units}<br><span class="muted">${pStr(h.g.p[h.i][h.j])} · ${h.g.sig[h.i][h.j] ? t("common.significant") : t("common.notSignificant")}</span>`);
  const r = G.map.getContainer().getBoundingClientRect();
  showTip(html, r.left + e.point.x, r.top + e.point.y);
}
function clickCell(ll) {
  const h = gridAt(ll);
  if (!h) return;
  const la = h.g.lat[h.i], lo = h.g.lon[h.j];
  const [w, s, e, n] = h.g.bounds;
  setSelection([Math.max(w, lo - h.dn / 2), Math.max(s, la - h.dl / 2), Math.min(e, lo + h.dn / 2), Math.min(n, la + h.dl / 2)], true);
}

// ---------------------------------------------------------------- selection, compute, result
function setSelection(b, final, preserveAnalysis = false) {
  G.sel = b;
  G.map.getSource("sel").setData({ type: "FeatureCollection", features: b ? [rectPoly(b)] : [] });
  if (!preserveAnalysis && (!b || final)) {
    G.lastAnalysis = null;
    resetSimilarAreas();
  }
  if (!final) return;
  const [w, s, e, n] = b;
  $("#gResult").hidden = false;
  const coordinate = (value) => I18N.number(value, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  $("#gSelInfo").textContent = t("globe.selectionCoordinates", { south: coordinate(s), north: coordinate(n), west: coordinate(w), east: coordinate(e), width: coordinate(e - w), height: coordinate(n - s) });
  $("#gModel").innerHTML = CAT.variables.map((v) => {
    const L = CAT.compute_limits[v.source];
    const tooBig = (e - w) > L.max_side_deg || (n - s) > L.max_side_deg || (e - w) * (n - s) > L.max_area_deg2;
    return `<option value="${v.id}" ${v.id === G.var ? "selected" : ""} ${tooBig ? "disabled" : ""}>${v.name.replace(/ \(.*\)/, "")}${tooBig ? t("globe.tooLargeSuffix") : ""}</option>`;
  }).join("");
  $("#gOut").innerHTML = `<p class="ginfo">${t("globe.downloadNotice")}</p>`;
  $("#gProg").hidden = true;
  Plotly.purge("gChart");
  // phones: the result panel sits under the globe, so show that something opened there
  if (PHONE() && $("#globe").classList.contains("active")) setTimeout(() => $("#gResult").scrollIntoView({ behavior: "smooth", block: "nearest" }), 350);
}
function legacyPowerBounds([w, s, e, n]) {
  const span = 2.02; // allow the legacy server to round the registered bounds to hundredths
  const expand = (lo, hi, limit) => {
    if (hi - lo >= 2) return [lo, hi];
    const start = Math.max(-limit, Math.min(limit - span, (lo + hi - span) / 2));
    return [start, start + span];
  };
  const [west, east] = expand(w, e, 180), [south, north] = expand(s, n, 89);
  return [west, south, east, north];
}
async function runCompute() {
  const selection = G.sel, varId = $("#gModel").value, displayedVar = G.var;
  if (!selection || !varId) return;
  G.lastAnalysis = null;
  resetSimilarAreas();
  const model = CAT.variables.find((v) => v.id === varId);
  const needsLegacyPadding = model.source === "power" && !CAT.compute_limits.power.pads_small_areas &&
    !CAT.regions.some((r) => available(varId, r.id) && coversPlace(r.bbox, selection));
  const requestBox = needsLegacyPadding ? legacyPowerBounds(selection) : selection;
  $("#gGo").disabled = true; $("#gOut").innerHTML = "";
  $("#gPendingPlace").hidden = false;
  let message = t("globe.areaAnalysisUnavailable");
  try {
    const r = await fetch("/api/compute", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ var: varId, bbox: requestBox }) });
    const j = await r.json();
    if (!r.ok) {
      if ([400, 429].includes(r.status) && typeof j.detail === "string") message = I18N.text(j.detail);
      throw new Error(message);
    }
    if (j.status !== "ready") {
      $("#gProg").hidden = false;
      $("#gProgMsg").textContent = t("globe.downloading", { seconds: j.estimate_s || "?" });
      while (true) {
        await new Promise((res) => setTimeout(res, 1500));
        const s = await api(`jobs/${j.job}`, "");
        if (s.status === "error") {
          message = t("globe.areaDownloadUnavailable");
          throw new Error(message);
        }
        if (G.sel === selection) {
          $("#gProgBar").style.width = Math.round((s.progress || 0) * 100) + "%";
          $("#gProgMsg").textContent = t("common.progressMessage", { message: s.message, seconds: Math.round(s.elapsed_s) });
        }
        if (s.status === "done") break;
      }
      $("#gProg").hidden = true;
      CAT = await api("catalog", "");
    } else if (!available(varId, j.region)) {
      CAT = await api("catalog", "");
    }
    const [w, s, e, n] = j.bbox;
    const bbox = [Math.max(w, selection[0]), Math.max(s, selection[1]), Math.min(e, selection[2]), Math.min(n, selection[3])];
    const source = CAT.regions.find((region) => region.id === j.region);
    const existing = savedPlaces().some((l) => sameBox(l.bbox, bbox));
    if (!existing && source && source.custom && sameBox(source.bbox, bbox)) {
      AREAS.add(j.region);
    } else {
      saveGlobePlace(varId, j.region, bbox);
    }
    if (G.sel === selection && G.var === displayedVar && varId !== G.var) {
      $("#gVar").value = varId;
      $("#gVar").dispatchEvent(new Event("change"));
    } else if (varId === G.var) loadLayers();
    const a = await api("analysis", new URLSearchParams({ var: varId, region: j.region, bbox: bbox.join(",") }));
    if (G.sel === selection) showResult(a, j.region);
  } catch {
    $("#gProg").hidden = true;
    if (G.sel === selection) $("#gOut").innerHTML = `<p class="ginfo" role="status">${esc(message)}</p>`;
  } finally {
    $("#gPendingPlace").hidden = true;
    $("#gGo").disabled = false;
  }
}
function showResult(a, region) {
  G.lastAnalysis = { raw: a._raw || a, region };
  renderSimilarAreas();
  const r = a.result, ver = a.verdict, v = CAT.variables.find((x) => x.id === a.variable);
  $("#gOut").innerHTML = `<div class="verdict ${ver.code}"><h2>${ver.title}</h2></div>
    <div class="big">${r.slope > 0 ? "+" : ""}${fmt(r.slope)} <small>${a.trend_units}</small></div>
    <div class="ginfo">${pStr(r.p)} · ${a.start}–${a.end}</div>
    <p class="ginfo"><span class="tag">${v.kind}</span>${v.product}</p>
    <button id="gOpen" class="btn">${t("globe.fullAnalysis")}${ic("arrow")}</button>`;
  const s = a.series, x = s.dates.map((d) => d + "-15");
  plot("gChart", [
    { x, y: s.anomaly, type: "scatter", mode: "lines", line: { color: "#8aa4bf", width: 1 }, name: t("charts.month") },
    ...(s.running12 ? [{ x, y: s.running12, type: "scatter", mode: "lines", line: { color: "#5ea8ff", width: 2 }, name: t("charts.runningMean") }] : []),
    { x, y: s.fit, type: "scatter", mode: "lines", line: { color: "#ff7b5c", width: 2.5 }, name: t("charts.trend") },
  ], layoutBase({ showlegend: false, margin: { l: 36, r: 6, t: 4, b: 24 }, font: { size: 10, color: "#dfe7ef" },
    xaxis: { gridcolor: "#2a3542", linecolor: "#2a3542" }, yaxis: { gridcolor: "#2a3542", linecolor: "#2a3542", zerolinecolor: "#4b5a6a" } }));
  $("#gOpen").onclick = () => {
    Object.assign(state, { var: a.variable, region, start: a.start, end: a.end, months: ALL, bbox: a.bbox });
    document.querySelector('.tab[data-tab="atlas"]').click();
    syncControls(); refresh(true);
  };
}

// ---------------------------------------------------------------- controls
function buildGlobeControls() {
  $("#gVar").innerHTML = CAT.variables.map((v) => `<option value="${v.id}">${v.name}</option>`).join("");
  $("#gVar").value = G.var;
  $("#gVar").onchange = (e) => {
    G.var = e.target.value;
    resetSimilarAreas();
    stopPlay();
    G.places = [];
    $$("#gRegions [data-r]:not(#gWorld)").forEach((b) => b.remove());
    if (G.map.getSource("regions")) {
      applyGlobePlace();
      $("#gPlaceNote").textContent = t("globe.loadingCoverage");
    }
    loadLayers();
  };
  $("#gWorld").onclick = () => selectGlobePlace("world");
  $$("#gMode .ibtn").forEach((c) => c.onclick = () => {
    G.mode = c.dataset.mode; $$("#gMode .ibtn").forEach((x) => { x.classList.toggle("on", x === c); x.setAttribute("aria-checked", x === c); });
    syncGlobeDisplay();
    stopPlay(); drawData();
  });
  $("#gYear").oninput = (e) => { G.year = +e.target.value; $("#gYearV").textContent = G.year; onYear(); };
  $("#gPlay").onclick = () => G.playing ? stopPlay() : startPlay();
  $("#gImagery").innerHTML = Object.entries(IMAGERY).map(([k, L]) => `<option value="${k}">${t(`globe.imageryLayers.${k}`)}</option>`).join("");
  $("#gImagery").onchange = (e) => { G.imagery = e.target.value; syncGlobeDisplay(); setImagery(); };
  $("#gImgMonth").onchange = (e) => { G.imgMonth = +e.target.value; setImagery(); };
  $("#gOpacity").oninput = (e) => {
    G.opacity = +e.target.value;
    G.grids.forEach((g) => G.map.setPaintProperty(g.id, "raster-opacity", G.opacity));
    if (G.map.getLayer("global-monthly")) G.map.setPaintProperty("global-monthly", "raster-opacity", G.opacity);
  };
  $("#gShow").onchange = (e) => {
    syncGlobeDisplay();
    if (!e.target.checked) stopPlay();
    drawData();
  };
  $("#gFade").onclick = () => { setPressed($("#gFade"), !pressed($("#gFade"))); drawData(); };
  $("#gDraw").onclick = () => {
    setDrawing(!G.drawing);
    // phones: the controls sit under the globe, so bring the globe into view to draw on it
    if (G.drawing && PHONE()) $("#globeMap").scrollIntoView({ behavior: "smooth", block: "start" });
  };
  $("#gGo").onclick = runCompute;
  $("#gSimilarToggle").onclick = () => {
    if (similar.opened) { resetSimilarAreas(); return; }
    similar.opened = true;
    renderSimilarAreas();
    if ($("#gSimilarForm").checkValidity()) searchSimilarAreas();
  };
  $("#gSimilarForm").onsubmit = (event) => { event.preventDefault(); searchSimilarAreas(); };
  $("#gSimilarList").onclick = (event) => {
    const target = event.target.closest("button");
    if (!target) return;
    if (target.hasAttribute("data-match")) { focusSimilarArea(+target.dataset.match); return; }
    const a = similarReference(), match = similar.result && similar.result.matches[+target.dataset.saveMatch];
    if (!a || !match) return;
    saveGlobePlace(a.variable, "world", match.bbox);
    target.textContent = t("similar.saved");
    target.disabled = true;
    loadLayers();
  };
  $("#gClose").onclick = () => { $("#gResult").hidden = true; setSelection(null, false); };
  if (!G.controlsReady) {
    G.controlsReady = true;
    $$(".tab").forEach((tab) => tab.addEventListener("click", () => { if (tab.dataset.tab === "globe" && G.map) setTimeout(() => G.map.resize(), 50); }));
  }
}
function syncGlobeDisplay() {
  const monthly = Boolean(G.monthly), show = $("#gShow").checked, imageryYear = Boolean(IMAGERY[G.imagery].time);
  $("#gMode").hidden = monthly;
  $("#gPlay").hidden = monthly;
  $("#gFade").hidden = monthly || G.mode !== "trend";
  $("#gYearRow").hidden = monthly && !imageryYear;
  $("#gYearRow").classList.toggle("dim", !monthly && G.mode !== "year" && !imageryYear);
  $("#gYear").setAttribute("aria-label", monthly ? t("globe.imageryYear") : t("common.year"));
  $$("#gMode .ibtn, #gFade, #gOpacity, #gPlay").forEach((el) => { el.disabled = !show; });
  $("#gYear").disabled = !show && !imageryYear;
  if (monthly && G.playing) stopPlay();
}
let yearTimer = null;
function onYear() {
  if (IMAGERY[G.imagery].time) setImagery();
  if (!G.monthly && G.mode === "year") { clearTimeout(yearTimer); yearTimer = setTimeout(drawData, 60); }
}
function startPlay() {
  if (G.mode !== "year") { $$("#gMode .ibtn").find((c) => c.dataset.mode === "year").click(); }
  const v = GV(); setPlayIcon(true);
  const token = {}; G.playing = token;
  const next = (y) => (y >= v.years[1] ? v.years[0] : y + 1);
  for (let y = G.year, k = 0; k < 4; k++) { y = next(y); prefetchYear(y); }
  (async function step() {
    while (G.playing === token) {
      const t0 = performance.now();
      G.year = next(G.year);
      $("#gYear").value = G.year; $("#gYearV").textContent = G.year;
      if (IMAGERY[G.imagery].time) setImagery();
      prefetchYear(next(next(next(G.year))));
      await drawData();
      await new Promise((r) => setTimeout(r, Math.max(0, 850 - (performance.now() - t0))));
    }
  })();
}
function setPlayIcon(on) {
  const b = $("#gPlay");
  b.innerHTML = ic(on ? "pause" : "play"); b.dataset.tip = on ? t("globe.pause") : t("globe.playYears"); b.setAttribute("aria-label", b.dataset.tip);
}
function stopPlay() { G.playing = null; setPlayIcon(false); }
let baseIdx = 0, baseKey = "", baseSwap = 0;
function setImagery() {
  const L = IMAGERY[G.imagery];
  const tiles = gibsTiles(G.imagery), key = tiles[0];
  $("#gImgMonth").hidden = !L.time;
  $("#gImgNote").textContent = L.time ? (G.year < L.from ? t("globe.imageryUnavailableBefore", { year: L.from }) : t("globe.imageryFollowsYear", { date: `${G.year}-${String(G.imgMonth).padStart(2, "0")}${L.time === "day" ? "-15" : ""}` })) : "";
  if (!G.map || key === baseKey) return;
  baseKey = key;
  // load the new date into the hidden base layer, then cross-fade once its tiles are in
  const nxt = 1 - baseIdx, src = G.map.getSource(`base${nxt}`), seq = ++baseSwap;
  src.setTiles(tiles); src.maxzoom = L.level;
  let done = false;
  const swap = () => {
    if (seq !== baseSwap || done) return;
    done = true;
    G.map.setPaintProperty(`base${nxt}`, "raster-opacity", 1);
    G.map.setPaintProperty(`base${baseIdx}`, "raster-opacity", 0);
    baseIdx = nxt;
    setPolarImagery(key);
  };
  const check = () => {
    if (seq !== baseSwap) { G.map.off("sourcedata", check); return; }
    if (G.map.isSourceLoaded(`base${nxt}`)) { G.map.off("sourcedata", check); swap(); }
  };
  G.map.on("sourcedata", check);
  setTimeout(() => { G.map.off("sourcedata", check); swap(); }, 2500); // never wait forever
}

function localiseGlobeCredits() {
  if (G.credits) G.map.removeControl(G.credits);
  G.credits = new maplibregl.AttributionControl({ compact: true, customAttribution: t("globe.attribution", {
    imagery: '<a href="https://earthdata.nasa.gov/gibs" target="_blank" rel="noopener">NASA GIBS</a>',
    borders: "Natural Earth", stars: "Yale BSC",
  }) });
  G.map.addControl(G.credits, "bottom-right");
  // small screens: start with the credits folded into the (i) button
  const attrib = G.map.getContainer().querySelector(".maplibregl-ctrl-attrib");
  if (PHONE() && attrib) attrib.classList.remove("maplibregl-compact-show");
}

window.localiseGlobe = async () => {
  const last = G.lastAnalysis;
  const model = $("#gModel").value;
  buildGlobeControls(); setPlayIcon(Boolean(G.playing));
  if (G.drawing) setDrawing(true);
  if (G.map) {
    localiseGlobeCredits();
    G.map.getCanvas().setAttribute("aria-label", t("mapControls.dragPan"));
    [
      [".maplibregl-ctrl-zoom-in", "mapControls.zoomIn"],
      [".maplibregl-ctrl-zoom-out", "mapControls.zoomOut"],
      [".maplibregl-ctrl-compass", "mapControls.resetBearing"],
      [".maplibregl-ctrl-attrib-button", "mapControls.attributionToggle"],
    ].forEach(([selector, key]) => {
      const button = G.map.getContainer().querySelector(selector);
      if (button) { button.title = t(key); button.setAttribute("aria-label", t(key)); }
    });
  }
  if (G.map && G.map.getSource("regions")) {
    await loadLayers(G.allPlacesVar === G.var && G.allPlaces ? I18N.response("layers", G.allPlaces.map((layer) => layer._raw || layer)) : undefined);
  }
  if (G.sel && !$("#gGo").disabled) {
    setSelection(G.sel, true, true);
    if (model) $("#gModel").value = model;
    if (last) showResult(I18N.response("analysis", last.raw), last.region);
  }
};

window.refreshGlobeAreas = () => { if (G.map && G.map.getSource("regions")) loadLayers(); };
window.initGlobeTab = function () {
  $("#gShowOthers").onchange = (e) => { AREAS.setOthers(e.target.checked); loadLayers(); if (CAT) syncControls(); }; buildGlobeControls(); initGlobe(); };
