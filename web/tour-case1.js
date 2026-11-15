/* Earth Evidence Atlas – Case 1 guided tour: "Is the ground heating up in the Amazon arc?" (engine: web/tour.js).
   Texts come from web/locales (tour.*), every number from the API responses the app already shows (events
   globe:result and atlas:analysis). The tour never starts a compute job: the ghost draws inside the built
   amazon_arc cube, so /api/compute answers "ready" at once.
   First visit only: a small offer card. Returning visitors start it from the "Guided tour" button.
   URL: ?tour=case1 starts it, ?tour=watch plays it, ?tour=0 keeps it away (tests, screenshots). */
(() => {
  "use strict";
  if (!window.AtlasTourEngine) return;
  const E = window.AtlasTourEngine;
  const AMAZON = [-64, -13, -54, -7], BOX = [-62, -12, -56, -8];
  const OFFERED = "atlas.tour.offered";
  const SHARED_LINK = location.hash.length > 1; // read before app.js writes its own state into the hash
  const has = (key) => t(key) !== key;
  const inside = (b) => Array.isArray(b) && b[0] >= AMAZON[0] && b[1] >= AMAZON[1] && b[2] <= AMAZON[2] && b[3] <= AMAZON[3];
  const shortPlace = (id) => has(`catalog.regions.${id}.shortName`) ? t(`catalog.regions.${id}.shortName`) : id;
  const common = () => ({ place: shortPlace("amazon_arc"), select: t("common.selectArea"), analyse: t("common.analyse"),
    copy: t("common.copyLink"), tour: t("tour.launch") });
  // a step text: touch variant when there is one, data from the app, app labels; parameters are escaped
  const say = (key, extra) => (ctx) => {
    const k = ctx.touch && has(key + "Touch") ? key + "Touch" : key;
    return I18N.html(k, Object.assign(common(), ctx.data, extra ? extra(ctx) : {}));
  };
  const word = (key) => () => t(key);

  // ---------------------------------------------------------------- numbers from the app's own responses
  const SEASONS = { "12,1,2": "djf", "3,4,5": "mam", "6,7,8": "jja", "9,10,11": "son" };
  function season(months) { // the period says which months it covers, so a seasonal result is never read as all-year
    const m = (months || []).slice().sort((x, y) => x - y).join(",");
    if (!m || m === "1,2,3,4,5,6,7,8,9,10,11,12") return "";
    const key = SEASONS[m === "1,2,12" ? "12,1,2" : m];
    return key ? t(`calendar.seasons.${key}.label`) : t("calendar.selectedMonths");
  }
  function numbers(a) {
    const r = a && a.result;
    if (!r || !Number.isFinite(r.slope)) return {};
    const months = season(a.months);
    return {
      rate: `${r.slope > 0 ? "+" : ""}${fmt(r.slope)} ${a.trend_units}`,
      ci: `${fmt(r.ci_low)} – ${fmt(r.ci_high)}`,
      p: pStr(r.p),
      period: `${a.start}–${a.end}` + (months ? `, ${months}` : ""),
      verdict: a.verdict && a.verdict.title ? a.verdict.title : "",
    };
  }
  window.addEventListener("globe:result", (e) => { if (tour.active) tour.set(numbers(e.detail)); });
  window.addEventListener("atlas:analysis", (e) => {
    if (!tour.active) return;
    const a = e.detail, rob = a.verdict && a.verdict.robustness;
    tour.set(Object.assign(numbers(a), {
      question: a.answer && a.answer.question ? a.answer.question : "",
      place: shortPlace(state.region),
      same: rob ? rob.same_sign : null, windows: rob ? rob.windows : null,
    }));
  });

  // ---------------------------------------------------------------- case board
  let board = null, lit = {};
  function makeBoard() {
    board = E.createCaseBoard({ labels: (k) => (has(`tour.labels.${k}`) ? t(`tour.labels.${k}`) : null) });
    Object.keys(lit).forEach((k) => board.light(k, lit[k]));
  }
  const light = (slot, value) => { lit[slot] = value == null ? "" : value; if (board) board.light(slot, lit[slot]); };

  // the Detective chart's trend line in screen points, for the ghost to trace
  function trendLine() {
    const gd = document.getElementById("chart"), L = gd && gd._fullLayout, tr = gd && gd.data && gd.data[gd.data.length - 1];
    if (!L || !tr || !tr.x || tr.x.length < 2) return [[0.08, 0.7], [0.95, 0.3]];
    const xa = L.xaxis, ya = L.yaxis, box = gd.getBoundingClientRect(), n = tr.x.length;
    return [0, Math.floor(n / 3), Math.floor((2 * n) / 3), n - 1].map((i) => ({
      x: box.left + xa._offset + xa.l2p(xa.d2l(tr.x[i])), y: box.top + ya._offset + ya.l2p(ya.d2l(tr.y[i])),
    }));
  }
  const openTab = (tab) => {
    const b = document.getElementById(`tab-${tab}`);
    if (b && !b.classList.contains("active")) b.click();
  };

  // ---------------------------------------------------------------- steps (chapters 1–2 of Appendix A, plus Resilience)
  const steps = [
    { id: "intro", chapter: "where", tab: "globe", title: word("tour.steps.intro.title"), text: say("tour.steps.intro.text"), dwell: 2600 },
    { id: "turn", chapter: "where", tab: "globe", targets: ["#globeMap"], padding: 0, radius: 0, text: say("tour.steps.turn.text"),
      ghost: { gesture: "drag", value: { from: [0.45, 0.5], to: [0.62, 0.46] }, action: () => AtlasGlobe.turn() },
      waitFor: { event: "globe:move" }, assist: 4000, dwell: 600 },
    { id: "var", chapter: "where", tab: "globe", targets: ["#gVar", "#gVarInfo"], title: word("tour.steps.var.title"), text: say("tour.steps.var.text"),
      ghost: { to: "#gVar", gesture: "select", value: "lst_day" }, waitFor: { predicate: () => $("#gVar").value === "lst_day" }, assist: 4000,
      after: () => light("what", t("tour.board.whatValue")) },
    { id: "place", chapter: "where", tab: "globe", targets: ['#gRegions [data-r="amazon_arc"]'], title: word("tour.steps.place.title"),
      text: say("tour.steps.place.text"), ghost: { gesture: "click", action: () => AtlasGlobe.selectPlace("amazon_arc") },
      waitFor: { predicate: () => AtlasGlobe.place === "amazon_arc" }, assist: 4000, after: () => light("where", shortPlace("amazon_arc")) },
    { id: "draw", chapter: "where", tab: "globe", targets: ["#gDraw", "#globeMap"], padding: 0, radius: 0, text: say("tour.steps.draw.text"),
      before: () => { if (AtlasGlobe.place !== "amazon_arc") AtlasGlobe.selectPlace("amazon_arc"); },
      ghost: { to: "#globeMap", gesture: "drag", action: () => AtlasGlobe.drawBox(BOX),
        value: () => ({ from: AtlasGlobe.project(BOX[0], BOX[3]), to: AtlasGlobe.project(BOX[2], BOX[1]) }) },
      waitFor: { event: "globe:selection", test: inside }, assist: 6000, lead: 1200 },
    { id: "analyse", chapter: "where", tab: "globe", targets: ["#gModel", "#gGo"], title: word("tour.steps.analyse.title"), text: say("tour.steps.analyse.text"),
      before: () => {
        const m = $("#gModel");
        if (m && Array.from(m.options).some((o) => o.value === "lst_day" && !o.disabled)) m.value = "lst_day";
      },
      ghost: { to: "#gGo", gesture: "click" }, waitFor: { event: "globe:result" }, assist: 4000,
      after: (ctx) => { if (ctx.data.rate) { light("howMuch", ctx.data.rate); light("significant", ctx.data.p); } } },
    { id: "result", chapter: "where", tab: "globe", targets: ["#gOut", "#gOpen"], lead: 2600,
      text: (ctx) => say(ctx.data.rate ? "tour.steps.result.text" : "tour.steps.result.noData", () => ({ open: t("globe.fullAnalysis") }))(ctx),
      ghost: { to: "#gOpen", gesture: "click" }, waitFor: { event: "atlas:tab", test: (v) => v === "atlas" }, assist: 6000 },
    { id: "answer", chapter: "hold", tab: "atlas", targets: ["#answer"], title: word("tour.steps.answer.title"), text: say("tour.steps.answer.text"),
      before: () => tour.waitReady("#answer .answer-head", 8000), dwell: 3600 },
    { id: "chart", chapter: "hold", tab: "atlas", targets: ["#chart"], text: say("tour.steps.chart.text"), demo: true,
      ghost: { gesture: "path", value: trendLine }, dwell: 2400 },
    { id: "matrix", chapter: "hold", tab: "atlas", targets: ["#matrix"], demo: true, ghost: { gesture: "hover" }, dwell: 3200,
      text: (ctx) => say(ctx.data.windows ? "tour.steps.matrix.text" : "tour.steps.matrix.noData")(ctx) },
    { id: "season", chapter: "hold", tab: "atlas", targets: [".seasons"], optional: true, text: say("tour.steps.season.text", () => ({ season: t("calendar.seasons.jja.label") })),
      ghost: { to: '.seasons [data-m="6,7,8"]', gesture: "click" }, assist: 5000,
      waitFor: { event: "atlas:analysis", test: (a) => (a.months || []).join(",") === "6,7,8" } },
    { id: "resilience", chapter: "use", tab: "atlas", targets: ["#detectiveResilience"], readyTimeout: 3000, title: word("tour.steps.resilience.title"),
      text: say("tour.steps.resilience.text", () => ({ open: t("resilience.openBrief") })), ghost: { gesture: "click" },
      waitFor: { event: "atlas:tab", test: (v) => v === "resilience" }, assist: 5000 },
    { id: "cards", chapter: "use", tab: "resilience", targets: ["#resilience-card-t2m", "#resilience-card-lst_day"], readyTimeout: 10000,
      text: say("tour.steps.cards.text"), dwell: 3600 },
    { id: "final", chapter: "use", title: word("tour.steps.final.title"), dwell: 4500,
      before: (ctx) => { if (ctx.data.rate) { light("howMuch", ctx.data.rate); light("significant", ctx.data.p); } },
      text: (ctx) => say(ctx.data.rate && ctx.data.question ? "tour.steps.final.text" : "tour.steps.final.noData")(ctx) },
  ];

  const tour = E.create({
    steps,
    chapters: [{ id: "where", title: word("tour.chapters.where") }, { id: "hold", title: word("tour.chapters.hold") }, { id: "use", title: word("tour.chapters.use") }],
    labels: (k) => (has(`tour.labels.${k}`) ? t(`tour.labels.${k}`) : null),
    hooks: { ensureTab: openTab },
    dwell: 1800,
    log: () => {}, // skipped steps are normal (e.g. Resilience unavailable for the area); keep the console clean
  });
  tour.on("start", () => { closeOffer(); lit = {}; if (board) board.remove(); makeBoard(); });
  tour.on("end", () => { if (board) { board.remove(); board = null; } lit = {}; });
  window.addEventListener("languagechange", () => {
    if (board) { board.remove(); makeBoard(); }
    tour.refresh();
    if (offerEl) { closeOffer(); offer(); }
  });

  function start(mode) {
    try { localStorage.setItem(OFFERED, "true"); } catch (e) { /* private mode */ }
    tour.start({ mode: mode || "guided" });
  }

  // ---------------------------------------------------------------- first-visit offer
  let offerEl = null;
  function closeOffer() { if (offerEl) { offerEl.remove(); offerEl = null; } }
  function offer() {
    const el = document.createElement("section");
    el.className = "atlas-tour-welcome";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-labelledby", "tourWelcomeTitle");
    el.innerHTML = `<h2 id="tourWelcomeTitle"></h2><p></p><div class="atlas-tour-actions">
      <button type="button" class="atlas-tour-btn atlas-tour-primary" data-act="start"></button>
      <button type="button" class="atlas-tour-btn atlas-tour-quiet" data-act="explore"></button></div>`;
    el.querySelector("h2").textContent = t("tour.welcome.title");
    el.querySelector("p").textContent = t("tour.welcome.text");
    el.querySelector('[data-act="start"]').textContent = t("tour.welcome.start");
    el.querySelector('[data-act="explore"]').textContent = t("tour.welcome.explore");
    el.querySelector('[data-act="start"]').onclick = () => { closeOffer(); start("guided"); };
    el.querySelector('[data-act="explore"]').onclick = closeOffer;
    el.addEventListener("keydown", (e) => { if (e.key === "Escape") closeOffer(); });
    document.body.appendChild(el);
    offerEl = el;
    el.querySelector('[data-act="start"]').focus({ preventScroll: true });
  }
  const firstVisit = () => {
    let seen = null;
    try { seen = localStorage.getItem(OFFERED); } catch (e) { return false; } // no storage: never nag on every load
    return !seen && tour.state.status === "new";
  };

  // wait until the app has its catalogue, texts and globe, then decide once
  function whenReady(fn, tries) {
    const ready = typeof CAT !== "undefined" && CAT && has("tour.launch") && document.querySelector("#gVar option") && window.AtlasGlobe && AtlasGlobe.ready;
    if (ready) fn(); else if ((tries || 0) < 150) setTimeout(() => whenReady(fn, (tries || 0) + 1), 200);
  }
  const param = E.parseTourParam(location.search);
  whenReady(() => {
    $("#tourLaunch").onclick = () => { closeOffer(); start("guided"); };
    if (param && param.disabled) return;
    if (param && param.mode === "watch") { setTimeout(() => start("watch"), 800); return; }
    if (param && param.mode === "guided") { setTimeout(() => start("guided"), 800); return; }
    // a shared link to an analysis (state in the hash) opens straight on that analysis, without an offer
    if (SHARED_LINK || !firstVisit()) return;
    setTimeout(() => {
      if (tour.active || !firstVisit()) return;
      try { localStorage.setItem(OFFERED, "true"); } catch (e) { return; } // shown once, even if the visitor just reloads
      offer();
    }, 1200);
  });
  window.AtlasTour = { start, stop: () => tour.stop(), tour };
})();
