/* Earth Evidence Atlas – guided tour engine: spotlight, ghost cursor, step bubble, step runner, case board.
   No dependencies and no build step. Exposes window.AtlasTourEngine. The engine holds no UI text of its own
   apart from default button labels (all injectable); step texts come from an injected t() or functions.
   It never calls the API: every number in a step comes from data the app passes in with tour.set(). */
(function (root) {
  "use strict";

  const DEFAULT_LABELS = {
    back: "Back", doIt: "Do it for me", skip: "Skip", next: "Next", done: "Finish", close: "End tour", stop: "Stop",
    progress: "Step {n} of {total}", board: "Case board",
    what: "What", where: "Where", howMuch: "How much", significant: "Significant?",
  };
  const READY_TIMEOUT = 8000, WAIT_TIMEOUT = 8000, SHEET_MAX = 900;

  // ------------------------------------------------------------------ pure helpers (no DOM, unit tested)
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const rect = (x, y, w, h) => ({ x, y, w, h });
  const validRect = (r) => !!r && isFinite(r.x) && isFinite(r.y) && r.w > 0 && r.h > 0;

  function unionRect(rects) {
    const list = (rects || []).filter(validRect);
    if (!list.length) return null;
    const x0 = Math.min.apply(null, list.map((r) => r.x)), y0 = Math.min.apply(null, list.map((r) => r.y));
    const x1 = Math.max.apply(null, list.map((r) => r.x + r.w)), y1 = Math.max.apply(null, list.map((r) => r.y + r.h));
    return rect(x0, y0, x1 - x0, y1 - y0);
  }
  function overlaps(a, b, gap) {
    return a.x < b.x + b.w + gap && b.x < a.x + a.w + gap && a.y < b.y + b.h + gap && b.y < a.y + a.h + gap;
  }
  // Overlapping (or nearly touching) rectangles become one: holes never cross, so the even-odd blocker stays exact.
  function mergeRects(rects, gap) {
    const g = gap || 0, list = (rects || []).filter(validRect).map((r) => rect(r.x, r.y, r.w, r.h));
    let changed = true;
    while (changed) {
      changed = false;
      for (let i = 0; i < list.length && !changed; i++) {
        for (let j = i + 1; j < list.length; j++) {
          if (overlaps(list[i], list[j], g)) { list[i] = unionRect([list[i], list[j]]); list.splice(j, 1); changed = true; break; }
        }
      }
    }
    return list.sort((a, b) => a.y - b.y || a.x - b.x);
  }
  const padRect = (r, pad) => rect(r.x - pad, r.y - pad, r.w + 2 * pad, r.h + 2 * pad);
  const fracPoint = (r, f) => ({ x: r.x + r.w * f[0], y: r.y + r.h * f[1] });

  // Where the step bubble goes: right, left, below, above (first that fits), shifted to stay on screen.
  function placeBubble(target, size, vp, opts) {
    const o = opts || {}, gap = o.gap == null ? 14 : o.gap, m = o.margin == null ? 12 : o.margin;
    if (o.sheet || vp.w <= (o.sheetMax || SHEET_MAX)) return { side: "sheet", x: 0, y: vp.h - size.h, arrow: null, fits: true };
    const center = () => ({ x: clamp((vp.w - size.w) / 2, m, Math.max(m, vp.w - m - size.w)), y: clamp((vp.h - size.h) / 2, m, Math.max(m, vp.h - m - size.h)) });
    if (!validRect(target)) return Object.assign({ side: "center", arrow: null, fits: true }, center());
    const room = {
      right: vp.w - (target.x + target.w) - gap - m, left: target.x - gap - m,
      bottom: vp.h - (target.y + target.h) - gap - m, top: target.y - gap - m,
    };
    const need = { right: size.w, left: size.w, bottom: size.h, top: size.h };
    const order = o.side ? [o.side] : (o.prefer || ["right", "left", "bottom", "top"]);
    let side = order.find((s) => room[s] >= need[s]);
    const fits = !!side;
    if (!side) side = o.side || "inside";
    const cx = target.x + target.w / 2, cy = target.y + target.h / 2;
    const xMax = Math.max(m, vp.w - m - size.w), yMax = Math.max(m, vp.h - m - size.h);
    let x, y;
    if (side === "right") { x = target.x + target.w + gap; y = cy - size.h / 2; }
    else if (side === "left") { x = target.x - gap - size.w; y = cy - size.h / 2; }
    else if (side === "bottom") { y = target.y + target.h + gap; x = cx - size.w / 2; }
    else if (side === "top") { y = target.y - gap - size.h; x = cx - size.w / 2; }
    else { x = vp.w - m - size.w; y = vp.h - m - size.h; } // target fills the screen: sit in its lower corner
    x = clamp(x, m, xMax); y = clamp(y, m, yMax);
    let arrow = null;
    if (side === "right" || side === "left") arrow = clamp(cy - y, 16, Math.max(16, size.h - 16));
    else if (side === "top" || side === "bottom") arrow = clamp(cx - x, 16, Math.max(16, size.w - 16));
    return { side, x, y, arrow, fits };
  }

  // One damped spring per hole coordinate (semi-implicit Euler, fixed sub-steps): settles in about 450 ms, ~1 % overshoot.
  const SPRING = { omega: 15, zeta: 0.82 };
  function springStep(x, v, target, dt, omega, zeta) {
    const w = omega || SPRING.omega, z = zeta || SPRING.zeta, n = Math.max(1, Math.ceil(dt / (1 / 240))), h = dt / n;
    for (let i = 0; i < n; i++) { v += (-2 * z * w * v - w * w * (x - target)) * h; x += v * h; }
    return [x, v];
  }
  const HOLE_KEYS = ["x", "y", "w", "h", "r"];
  function stepHole(hole, target, dt) {
    let settled = true;
    HOLE_KEYS.forEach((k) => {
      const vk = "v" + k, s = springStep(hole[k], hole[vk] || 0, target[k], dt);
      hole[k] = s[0]; hole[vk] = s[1];
      if (Math.abs(hole[k] - target[k]) < 0.25 && Math.abs(hole[vk]) < 2) { hole[k] = target[k]; hole[vk] = 0; } else settled = false;
    });
    return settled;
  }
  const lerpHole = (a, b, t) => { const o = {}; HOLE_KEYS.forEach((k) => { o[k] = a[k] + (b[k] - a[k]) * t; }); return o; };

  // Even-odd clip path: the whole screen minus every hole, so the blocker catches clicks only outside the holes.
  function holePath(rects, vw, vh) {
    const n = (v) => Math.round(v * 10) / 10;
    return `M0 0H${n(vw)}V${n(vh)}H0Z` + rects.filter(validRect).map((r) => `M${n(r.x)} ${n(r.y)}h${n(r.w)}v${n(r.h)}h${n(-r.w)}Z`).join("");
  }

  // Ghost flight: duration grows with distance (500–900 ms), path is a quadratic Bézier arc.
  const flightDuration = (dist) => Math.round(clamp(500 + dist * 0.6, 500, 900));
  function arcControl(a, b) {
    const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1, bend = Math.min(140, d * 0.25);
    let nx = -dy / d, ny = dx / d;
    if (ny > 0) { nx = -nx; ny = -ny; } // bow upwards, like a hand lifting the mouse
    return { x: (a.x + b.x) / 2 + nx * bend, y: (a.y + b.y) / 2 + ny * bend };
  }
  function bezierPoint(a, c, b, t) {
    const u = 1 - t;
    return { x: u * u * a.x + 2 * u * t * c.x + t * t * b.x, y: u * u * a.y + 2 * u * t * c.y + t * t * b.y };
  }
  const easeInOut = (t) => t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  function polylinePoint(pts, t) {
    if (pts.length < 2) return pts[0];
    const seg = [];
    let total = 0;
    for (let i = 1; i < pts.length; i++) { const d = Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y); seg.push(d); total += d; }
    let goal = clamp(t, 0, 1) * total;
    for (let i = 0; i < seg.length; i++) {
      if (goal <= seg[i] || i === seg.length - 1) {
        const f = seg[i] ? clamp(goal / seg[i], 0, 1) : 1;
        return { x: pts[i].x + (pts[i + 1].x - pts[i].x) * f, y: pts[i].y + (pts[i + 1].y - pts[i].y) * f };
      }
      goal -= seg[i];
    }
    return pts[pts.length - 1];
  }

  // How far to scroll so a target sits between top and bottom (the bottom sheet covers the lower screen on phones).
  function scrollDelta(r, top, bottom) {
    if (!validRect(r)) return 0;
    if (r.h > bottom - top || r.y < top) return Math.round(r.y - top);
    if (r.y + r.h > bottom) return Math.round(r.y + r.h - bottom);
    return 0;
  }

  // ?tour=case1 → guided, ?tour=watch → watch, ?tour=0 → off. No autostart here: the app decides.
  function parseTourParam(search) {
    let v = null;
    try { v = new URLSearchParams(search || "").get("tour"); } catch (e) { return null; }
    if (v === null) return null;
    if (v === "0" || v === "off" || v === "false") return { disabled: true, mode: "free", tour: null };
    if (v === "watch") return { disabled: false, mode: "watch", tour: null };
    return { disabled: false, mode: "guided", tour: v || null };
  }

  const fill = (s, p) => String(s).replace(/\{(\w+)\}/g, (w, k) => p[k] == null ? w : String(p[k]));

  // ------------------------------------------------------------------ saved progress (localStorage through try/catch)
  function createStore(key, storage) {
    const blank = () => ({ v: 1, status: "new", step: null, chapter: null, done: [], skipped: [] });
    const box = () => storage || root.localStorage;
    return {
      blank,
      read() {
        try { const v = JSON.parse(box().getItem(key)); return v && v.v === 1 ? Object.assign(blank(), v) : blank(); } catch (e) { return blank(); }
      },
      write(state) { try { box().setItem(key, JSON.stringify(state)); } catch (e) { /* private mode: keep going without saving */ } },
      clear() { try { box().removeItem(key); } catch (e) { /* nothing saved */ } },
    };
  }

  // ------------------------------------------------------------------ environment (replaced by a fake clock in tests)
  function browserEnv() {
    return {
      now: () => root.performance.now(),
      setTimeout: (f, ms) => root.setTimeout(f, ms),
      clearTimeout: (h) => root.clearTimeout(h),
      frame: (f) => root.requestAnimationFrame(f),
      cancelFrame: (h) => root.cancelAnimationFrame(h),
      query: (s) => typeof s === "string" ? root.document.querySelector(s) : s || null,
      measure(el) {
        if (!el || !el.isConnected || !el.getClientRects().length) return null;
        if (root.getComputedStyle(el).visibility === "hidden") return null;
        const r = el.getBoundingClientRect();
        return r.width < 1 && r.height < 1 ? null : rect(r.left, r.top, r.width, r.height);
      },
      listen(target, type, fn, opts) { target.addEventListener(type, fn, opts); return () => target.removeEventListener(type, fn, opts); },
      window: root,
      document: root.document,
    };
  }

  // Default real actions; the app injects its own (e.g. drawBox on the globe). They run the same code a user would.
  const DEFAULT_ACTIONS = {
    click(el) { el.click(); },
    setValue(el, value) {
      el.value = value;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    },
    hover(el, pt) {
      const at = root.document.elementFromPoint(pt.x, pt.y), target = at && el.contains(at) ? at : el;
      ["pointermove", "mouseover", "mousemove"].forEach((type) => {
        const E = type.startsWith("pointer") && root.PointerEvent ? root.PointerEvent : root.MouseEvent;
        target.dispatchEvent(new E(type, { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, pointerId: 1, isPrimary: true, pointerType: "mouse" }));
      });
    },
    drag(el, from, to) {
      if (el.tagName === "INPUT" && el.type === "range") { // a slider: set the value under the end point
        const r = el.getBoundingClientRect(), f = clamp((to.x - r.left) / (r.width || 1), 0, 1);
        const min = +el.min || 0, max = el.max === "" ? 100 : +el.max, step = +el.step || 1;
        DEFAULT_ACTIONS.setValue(el, String(Math.round((min + f * (max - min)) / step) * step));
        return;
      }
      const send = (type, pt) => {
        const E = root.PointerEvent || root.MouseEvent;
        el.dispatchEvent(new E(type, { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, button: 0, buttons: type === "pointerup" ? 0 : 1, pointerId: 1, isPrimary: true, pointerType: "mouse" }));
      };
      send("pointerdown", from);
      for (let i = 1; i <= 8; i++) send("pointermove", { x: from.x + (to.x - from.x) * i / 8, y: from.y + (to.y - from.y) * i / 8 });
      send("pointerup", to);
    },
  };

  // ------------------------------------------------------------------ step runner
  function createTour(options) {
    const o = Object.assign({ mode: "guided", storageKey: "atlas.tour.v1", readyTimeout: READY_TIMEOUT, waitTimeout: WAIT_TIMEOUT,
      dwell: 1800, watchLead: 500, iconHref: "/static/icons.svg" }, options || {});
    const steps = o.steps || [], chapters = o.chapters || [];
    const env = o.env || browserEnv();
    const store = createStore(o.storageKey, o.storage);
    const actions = Object.assign({}, DEFAULT_ACTIONS, o.actions || {});
    const listeners = {}, data = {}, timers = new Set();
    let st = store.read(), mode = "free", index = -1, runId = 0, active = false, paused = false, ui = null;
    let current = null, decide = null, stepOffs = [], globalOffs = [];

    const label = (k) => typeof o.labels === "function" ? (o.labels(k) || DEFAULT_LABELS[k]) : Object.assign({}, DEFAULT_LABELS, o.labels || {})[k];
    const log = function () { const a = Array.prototype.slice.call(arguments); if (o.log) o.log.apply(null, a); else if (root.console) root.console.info.apply(root.console, ["[tour]"].concat(a)); };
    const emit = (name, detail) => (listeners[name] || []).slice().forEach((fn) => { try { fn(detail); } catch (e) { log("listener failed", name, e); } });
    const save = () => { if (mode !== "watch") store.write(st); };
    const mark = (id, kind) => {
      st.done = st.done.filter((x) => x !== id); st.skipped = st.skipped.filter((x) => x !== id);
      st[kind === "done" ? "done" : "skipped"].push(id); save();
    };
    const touch = () => !!(env.window && env.window.matchMedia && env.window.matchMedia("(pointer: coarse)").matches);
    const phone = () => !!(env.window && env.window.innerWidth <= SHEET_MAX);
    const context = (step) => ({ step, index, mode, data, touch: touch(), phone: phone(), t: o.t, tour: api });
    function text(spec, ctx) {
      if (spec == null) return "";
      if (typeof spec === "function") return String(spec(ctx));
      return o.t ? String(o.t(spec, ctx.data)) : String(spec);
    }

    // timers that stop while the page is hidden
    function timer(ms, fn) {
      const tm = { left: ms, start: env.now(), h: null, done: false };
      const fire = () => { tm.done = true; tm.h = null; timers.delete(tm); fn(); };
      tm.cancel = () => { if (tm.h != null) env.clearTimeout(tm.h); tm.h = null; tm.done = true; timers.delete(tm); };
      tm.pause = () => { if (tm.h != null) { env.clearTimeout(tm.h); tm.h = null; tm.left -= env.now() - tm.start; } };
      tm.resume = () => { if (!tm.done && tm.h == null) { tm.start = env.now(); tm.h = env.setTimeout(fire, Math.max(0, tm.left)); } };
      timers.add(tm);
      if (!paused) tm.h = env.setTimeout(fire, ms);
      return tm;
    }
    const sleep = (ms) => new Promise((res) => { const tm = timer(ms, res); stepOffs.push(() => { if (!tm.done) { tm.cancel(); res(); } }); });

    // check once per frame until true, or until the timeout (0 = none) or alive() turns false
    function poll(check, timeout, alive) {
      return new Promise((resolve) => {
        let end = false, fh = null, tm = null;
        const finish = (v) => {
          if (end) return;
          end = true;
          if (fh != null && env.cancelFrame) env.cancelFrame(fh);
          if (tm) tm.cancel();
          resolve(v);
        };
        if (timeout > 0) tm = timer(timeout, () => finish(false));
        const tick = () => {
          fh = null;
          if (end) return;
          if (!alive()) return finish(false);
          let ok = false;
          if (!paused) { try { ok = !!check(); } catch (e) { log("check failed", e); } }
          if (ok) finish(true); else fh = env.frame(tick);
        };
        tick();
      });
    }

    // visible and the same size and place for 2 frames, or null after the timeout
    function waitReady(selector, timeout, run) {
      const r0 = run == null ? runId : run;
      let last = null, stable = 0, found = null;
      return poll(() => {
        const el = env.query(selector), r = el ? env.measure(el) : null;
        if (!r) { last = null; stable = 0; return false; }
        const same = last && ["x", "y", "w", "h"].every((k) => Math.abs(r[k] - last[k]) < 0.5);
        stable = same ? stable + 1 : 0; last = r; found = el;
        return stable >= 2;
      }, timeout == null ? o.readyTimeout : timeout, () => r0 === runId).then((ok) => ok ? found : null);
    }

    // waitFor: { event, on?, target?, test? } and/or { predicate }; resolves "ok", "timeout", "next" or "cancel"
    function makeWaiter(spec, run, ctx, dir) {
      const offs = [];
      let end = false, armed = null, resolveFn;
      const promise = new Promise((r) => { resolveFn = r; });
      const finish = (v) => {
        if (end) return;
        end = true; offs.forEach((f) => f()); if (armed) armed.cancel(); resolveFn(v);
      };
      if (spec.event) {
        const target = spec.on ? env.query(spec.on) : (spec.target || env.window);
        if (target) {
          offs.push(env.listen(target, spec.event, (e) => {
            let ok = true;
            if (spec.test) { try { ok = !!spec.test(e && e.detail, e, ctx); } catch (er) { ok = false; log("test failed", ctx.step.id, er); } }
            if (ok) finish("ok");
          }));
        } else log("waitFor target missing", ctx.step.id, spec.on);
      }
      if (spec.predicate) {
        let seenFalse = dir >= 0; // coming back with Back: wait for a real change, do not bounce straight forward
        poll(() => { const v = !!spec.predicate(ctx); if (!v) seenFalse = true; return v && seenFalse; }, 0, () => !end && run === runId)
          .then((ok) => { if (ok) finish("ok"); });
      }
      return { promise, finish, arm(ms) { if (!end && !armed) armed = timer(ms, () => finish("timeout")); }, get done() { return end; } };
    }

    function cleanupStep() {
      const offs = stepOffs; stepOffs = [];
      offs.forEach((f) => { try { f(); } catch (e) { /* already gone */ } });
      if (current && current.waiter) current.waiter.finish("cancel");
      if (decide) { const d = decide; decide = null; d("cancel"); }
      if (ui) ui.cancelGhost();
      current = null;
    }

    function chapterDots(step) {
      const at = chapters.findIndex((c) => c.id === step.chapter);
      return chapters.map((c, i) => ({ id: c.id, title: text(c.title, context(step)), state: i < at ? "done" : i === at ? "current" : "todo" }));
    }
    function view(step, ctx, els, ghostEl) {
      return {
        id: step.id, title: text(step.title, ctx), html: text(step.text, ctx), chapters: chapterDots(step),
        progress: fill(label("progress"), { n: index + 1, total: steps.length }), mode,
        canBack: mode === "guided" && index > 0, canDoIt: mode === "guided" && !!step.ghost && !!ghostEl,
        reading: !step.waitFor, last: index === steps.length - 1, targets: els, selectors: step.targets || [], ghostEl,
        padding: step.padding == null ? 6 : step.padding, radius: step.radius == null ? 10 : step.radius, side: step.side || null,
      };
    }

    function resolveValue(v, ctx) { return typeof v === "function" ? v(ctx) : v; }
    function ghostPoints(step, el) { // fractions of the target box → screen points (used without the DOM layer)
      const g = step.ghost, gesture = g.gesture || "click", r = env.measure(el) || rect(0, 0, 0, 0);
      let v = gesture === "select" || gesture === "click" ? {} : g.value || {}; // a select value is an option, not geometry
      if (gesture === "drag" && typeof v === "function") v = v(r) || {};
      const at = (f) => f.x != null ? f : fracPoint(r, f);
      const from = g.from || v.from || [0.3, 0.3], to = g.to2 || v.to || [0.7, 0.7];
      const hoverAt = g.at || (Array.isArray(v) && typeof v[0] === "number" ? v : [0.5, 0.5]);
      let pts = [[0.5, 0.5]];
      if (gesture === "hover") pts = [hoverAt];
      else if (gesture === "path") pts = typeof g.points === "function" ? g.points(r) : typeof v === "function" ? v(r) : (g.points || (Array.isArray(v) ? v : pts));
      return { from: at(from), to: at(to), points: pts.map(at) };
    }
    // the real action behind a gesture; `extra` carries points from the ghost animation
    function act(step, el, ctx, extra) {
      const g = step.ghost, x = extra || ghostPoints(step, el);
      emit("action", { step, gesture: g.gesture || "click" });
      if (g.action) return g.action(el, ctx, x);
      switch (g.gesture) {
        case "select": return actions.setValue(el, resolveValue(g.value, ctx), ctx);
        case "drag": return actions.drag(el, x.from, x.to, ctx);
        case "hover": case "path": return actions.hover(el, x.point || x.points[x.points.length - 1], ctx);
        default: return actions.click(el, ctx);
      }
    }
    function perform(step, el, real) {
      const ctx = current ? current.ctx : context(step);
      if (el && el.isConnected === false) { // the app re-rendered the control since the step started
        const again = env.query(step.ghost.to || (step.targets || [])[0]);
        if (again) { el = again; if (current) current.ghostEl = again; }
      }
      const doAct = (extra) => real ? act(step, el, ctx, extra) : undefined;
      const p = ui ? ui.perform(step, el, { real, act: doAct, value: resolveValue(step.ghost.value, ctx) })
        : Promise.resolve(real ? doAct() : undefined);
      return Promise.resolve(p).catch((e) => log("ghost action failed", step.id, e));
    }

    function armAssist(step, run) {
      if (!(step.assist > 0) || !step.ghost || !ui || !env.window) return;
      let tm = null, wait = step.assist;
      const arm = () => { if (tm) tm.cancel(); tm = timer(wait, fire); };
      const fire = () => {
        if (run !== runId || !current || current.busy) return arm();
        current.busy = perform(step, current.ghostEl, false).then(() => { if (current) current.busy = null; });
        wait = step.assist * 2; arm();
      };
      const reset = () => { if (run === runId) arm(); };
      ["pointerdown", "keydown", "wheel", "touchstart"].forEach((type) => stepOffs.push(env.listen(env.window, type, reset, { passive: true })));
      stepOffs.push(() => { if (tm) tm.cancel(); });
      arm();
    }

    async function go(i, dir) {
      const run = ++runId;
      cleanupStep();
      if (!active) return;
      if (i < 0) { i = 0; dir = 1; }
      if (i >= steps.length) return finish("done");
      index = i;
      const step = steps[i], ctx = context(step);
      st.step = step.id; st.chapter = step.chapter == null ? null : step.chapter; st.status = "active"; save();
      emit("step", { index: i, step, mode });
      try {
        if (ui) ui.busy(true);
        if (step.tab && o.hooks && o.hooks.ensureTab) await o.hooks.ensureTab(step.tab, ctx);
        if (run !== runId) return;
        if (step.before) await step.before(ctx);
        if (run !== runId) return;
        const sel = step.targets || [];
        let els = [];
        if (sel.length) {
          const found = await Promise.all(sel.map((s) => waitReady(s, step.readyTimeout == null ? o.readyTimeout : step.readyTimeout, run)));
          if (run !== runId) return;
          found.forEach((el, k) => { if (!el) log("target not found", step.id, sel[k]); });
          els = found.filter(Boolean);
          if (!els.length) {
            log("step skipped: no target", step.id);
            mark(step.id, "skipped"); emit("skip", { step, reason: "missing" });
            return go(i + (dir < 0 ? -1 : 1), dir < 0 && i === 0 ? 1 : dir);
          }
        }
        const ghostEl = step.ghost ? (step.ghost.to ? env.query(step.ghost.to) : els[0]) || null : null;
        current = { step, run, els, ghostEl, ctx, waiter: null, busy: null };
        if (ui) ui.show(view(step, ctx, els, ghostEl));
        const waiter = step.waitFor ? makeWaiter(step.waitFor, run, ctx, dir) : null;
        current.waiter = waiter;
        let outcome;
        if (mode === "watch") {
          await sleep(step.lead == null ? o.watchLead : step.lead);
          if (run !== runId) return;
          if (step.ghost && ghostEl) { current.busy = perform(step, ghostEl, true); await current.busy; }
          if (run !== runId) return;
          if (waiter) { waiter.arm(o.waitTimeout); outcome = await waiter.promise; } else outcome = "read";
          if (run !== runId) return;
          await sleep(step.dwell == null ? o.dwell : step.dwell);
        } else {
          if (step.demo && step.ghost && ghostEl && ui) current.busy = perform(step, ghostEl, false).then(() => { if (current) current.busy = null; });
          armAssist(step, run);
          if (waiter) outcome = await waiter.promise;
          else outcome = await new Promise((r) => { decide = r; });
          if (run !== runId) return;
          if (current && current.busy) await Promise.race([current.busy, sleep(1500)]);
        }
        if (run !== runId) return;
        if (outcome === "timeout") log("step timed out, moving on", step.id);
        if (step.after) await step.after(ctx, outcome);
        if (run !== runId) return;
        mark(step.id, "done"); emit("complete", { step, outcome });
        return go(i + 1, 1);
      } catch (e) {
        log("step failed", step.id, e);
        if (run === runId) { mark(step.id, "skipped"); emit("skip", { step, reason: "error" }); return go(i + 1, 1); }
      }
    }

    function finish(reason) {
      runId++;
      cleanupStep();
      globalOffs.forEach((f) => f()); globalOffs = [];
      timers.forEach((tm) => tm.cancel());
      if (ui) { ui.unmount(); ui = null; }
      const was = active;
      active = false; paused = false;
      if (was) {
        st.status = reason === "done" ? "done" : "dismissed"; save();
        emit("end", { reason, index, mode });
      }
      index = -1;
    }

    const api = {
      engine: "AtlasTourEngine",
      start(opts) {
        const so = opts || {};
        if (active) finish("restart");
        mode = so.mode || o.mode;
        if (mode === "free") { emit("end", { reason: "free", index: -1, mode }); return false; }
        st = store.read();
        let at = 0;
        if (so.at != null) at = typeof so.at === "number" ? so.at : Math.max(0, steps.findIndex((s) => s.id === so.at));
        else if (so.resume && mode === "guided" && st.step && st.status !== "done") at = Math.max(0, steps.findIndex((s) => s.id === st.step));
        if (!so.resume || mode === "watch") st = Object.assign(store.blank(), { status: "active" });
        active = true; paused = false;
        if (o.ui !== false && root.document) {
          ui = o.ui || createDomUI(o, env, {
            label, onBack: () => api.back(), onSkip: () => api.skip(), onDoIt: () => api.doIt(), onNext: () => api.next(),
            onClose: () => api.stop("dismissed"),
          });
          ui.mount(mode);
        } else ui = o.ui || null;
        if (env.document && env.document.addEventListener) {
          globalOffs.push(env.listen(env.document, "visibilitychange", () => { if (env.document.hidden) api.pause(); else api.resume(); }));
        }
        emit("start", { mode, index: at });
        go(at, 1);
        return true;
      },
      stop(reason) { if (active) finish(reason || "dismissed"); },
      next() { if (!active || !current) return; if (decide) { const d = decide; decide = null; d("next"); } else if (current.waiter) current.waiter.finish("next"); },
      back() { if (active && mode === "guided") go(Math.max(0, index - 1), -1); },
      skip() { if (!active || index < 0) return; const s = steps[index]; mark(s.id, "skipped"); emit("skip", { step: s, reason: "user" }); go(index + 1, 1); },
      doIt() {
        if (!active || !current) return;
        const c = current;
        if (!c.step.ghost || !c.ghostEl) { api.next(); return; }
        if (c.acting) return; // a second click while the ghost is already doing it
        if (ui) ui.cancelGhost();
        c.acting = true;
        c.busy = perform(c.step, c.ghostEl, true).then(() => { c.acting = false; });
        if (c.waiter) c.waiter.arm(o.waitTimeout); else c.busy.then(() => { if (current === c) api.next(); });
      },
      pause() { if (!active || paused) return; paused = true; timers.forEach((tm) => tm.pause()); if (ui) ui.pause(); emit("pause", {}); },
      resume() { if (!active || !paused) return; paused = false; timers.forEach((tm) => tm.resume()); if (ui) ui.resume(); emit("resume", {}); },
      set(values) { Object.assign(data, values || {}); api.refresh(); },
      refresh() { if (ui && current) ui.show(view(current.step, current.ctx, current.els, current.ghostEl), true); },
      reset() { store.clear(); st = store.blank(); },
      on(name, fn) { (listeners[name] = listeners[name] || []).push(fn); return () => { listeners[name] = (listeners[name] || []).filter((f) => f !== fn); }; },
      waitReady: (sel, timeout) => waitReady(sel, timeout),
      get state() { return JSON.parse(JSON.stringify(st)); },
      get index() { return index; },
      get step() { return index >= 0 ? steps[index] : null; },
      get mode() { return mode; },
      get active() { return active; },
      get paused() { return paused; },
      data,
      steps,
    };
    return api;
  }

  // ------------------------------------------------------------------ DOM layer: veil with holes, blocker, ghost, bubble
  function createDomUI(o, env, h) {
    const doc = root.document, win = root, NS = "http://www.w3.org/2000/svg";
    const mq = (q) => !!(win.matchMedia && win.matchMedia(q).matches);
    const reduced = () => mq("(prefers-reduced-motion: reduce)");
    const uid = "atlas-tour-" + Math.random().toString(36).slice(2, 8);
    let rootEl = null, maskG, glowG, trail, blocker, bubble, arrowEl, titleEl, bodyEl, dotsEl, countEl, actionsEl, ghost, btn = {};
    let mounted = false, frameH = null, lastT = 0, pausedAt = 0, holes = [], targets = [], model = null, mode = "guided";
    let tweens = [], ghostTok = 0, ghostPos = null, ghostIdle = null, lastClip = "", lastBubble = "", trailPts = [], scrollPending = false;

    const make = (tag, cls, attrs) => {
      const e = doc.createElement(tag);
      if (cls) e.className = cls;
      Object.keys(attrs || {}).forEach((k) => e.setAttribute(k, attrs[k]));
      return e;
    };
    const svgEl = (tag, attrs) => { const e = doc.createElementNS(NS, tag); Object.keys(attrs || {}).forEach((k) => e.setAttribute(k, attrs[k])); return e; };
    const toRect = (r) => rect(r.left, r.top, r.width, r.height);
    const vp = () => ({ w: win.innerWidth, h: win.innerHeight });
    const sheet = () => win.innerWidth <= SHEET_MAX;

    function mount(m) {
      mode = m;
      rootEl = make("div", "atlas-tour", { "data-mode": m });
      const svg = svgEl("svg", { class: "atlas-tour-veil", "aria-hidden": "true", focusable: "false" });
      const defs = svgEl("defs"), mask = svgEl("mask", { id: uid + "-mask", maskUnits: "userSpaceOnUse", x: "0", y: "0", width: "100%", height: "100%" });
      mask.appendChild(svgEl("rect", { x: "0", y: "0", width: "100%", height: "100%", fill: "#fff" }));
      maskG = svgEl("g", { fill: "#000" }); mask.appendChild(maskG); defs.appendChild(mask); svg.appendChild(defs);
      svg.appendChild(svgEl("rect", { class: "atlas-tour-dim", x: "0", y: "0", width: "100%", height: "100%", mask: `url(#${uid}-mask)` }));
      glowG = svgEl("g", { class: "atlas-tour-glow" }); svg.appendChild(glowG);
      trail = svgEl("path", { class: "atlas-tour-trail", d: "" }); svg.appendChild(trail);
      blocker = make("div", "atlas-tour-blocker");
      blocker.addEventListener("pointerdown", (e) => { e.preventDefault(); nudge(); });
      blocker.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); });
      ghost = make("div", "atlas-tour-ghost", { "aria-hidden": "true", "data-touch": mq("(pointer: coarse)") ? "1" : "0" });
      ghost.innerHTML = '<svg class="atlas-tour-ghost-arrow" viewBox="0 0 24 24" width="26" height="26"><path d="M4.5 2.5v17.2l4.6-4.3 3.1 6.6 3-1.4-3.1-6.5 6.3-.3z"/></svg><span class="atlas-tour-ghost-touch"></span>';
      bubble = make("div", "atlas-tour-bubble", { role: "dialog", "aria-modal": "false", "aria-labelledby": uid + "-title", "aria-describedby": uid + "-body", tabindex: "-1" });
      arrowEl = make("span", "atlas-tour-arrow", { "aria-hidden": "true" });
      const head = make("div", "atlas-tour-head");
      dotsEl = make("ol", "atlas-tour-dots");
      countEl = make("span", "atlas-tour-count");
      btn.close = make("button", "atlas-tour-x", { type: "button", "aria-label": h.label("close"), "data-tip": h.label("close") });
      btn.close.innerHTML = `<svg class="atlas-tour-ic" aria-hidden="true"><use href="${o.iconHref}#i-close"/></svg>`;
      head.append(dotsEl, countEl, btn.close);
      titleEl = make("h2", "atlas-tour-title", { id: uid + "-title" });
      bodyEl = make("div", "atlas-tour-body", { id: uid + "-body", "aria-live": "polite" });
      actionsEl = make("div", "atlas-tour-actions");
      btn.back = make("button", "atlas-tour-btn", { type: "button" });
      btn.skip = make("button", "atlas-tour-btn atlas-tour-quiet", { type: "button" });
      btn.doIt = make("button", "atlas-tour-btn", { type: "button" });
      btn.next = make("button", "atlas-tour-btn", { type: "button" });
      actionsEl.append(btn.back, btn.skip, btn.doIt, btn.next);
      bubble.append(arrowEl, head, titleEl, bodyEl, actionsEl);
      btn.back.addEventListener("click", h.onBack); btn.skip.addEventListener("click", h.onSkip);
      btn.doIt.addEventListener("click", h.onDoIt); btn.next.addEventListener("click", () => (mode === "watch" ? h.onClose() : h.onNext()));
      btn.close.addEventListener("click", h.onClose);
      bubble.addEventListener("keydown", onBubbleKey);
      doc.addEventListener("keydown", onKey, true);
      rootEl.append(svg, blocker, bubble, ghost);
      doc.body.appendChild(rootEl);
      doc.body.classList.add("atlas-tour-active");
      mounted = true;
      root.requestAnimationFrame(() => { if (rootEl) rootEl.classList.add("is-on"); });
      loop();
    }
    function unmount() {
      mounted = false;
      cancelGhost();
      if (frameH != null) root.cancelAnimationFrame(frameH);
      frameH = null;
      doc.removeEventListener("keydown", onKey, true);
      doc.body.classList.remove("atlas-tour-active");
      if (rootEl) rootEl.remove();
      rootEl = null; holes = []; targets = [];
    }
    function onKey(e) {
      if (e.key === "Escape" && mounted) { e.preventDefault(); h.onClose(); }
    }
    // Tab past the last bubble button goes to the spotlighted control, so the whole step works from the keyboard
    function onBubbleKey(e) {
      if (e.key !== "Tab" || e.shiftKey) return;
      const items = Array.from(bubble.querySelectorAll("button:not([hidden]):not([disabled])"));
      if (doc.activeElement !== items[items.length - 1]) return;
      const sel = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
      for (const el of targets) {
        const f = el.matches(sel) ? el : el.querySelector(sel);
        if (f) { e.preventDefault(); f.focus(); return; }
      }
    }

    function busy(on) {
      if (!bubble) return;
      bubble.setAttribute("aria-busy", on ? "true" : "false");
      [btn.back, btn.skip, btn.doIt, btn.next].forEach((b) => { b.disabled = !!on; });
    }

    function show(m, quiet) {
      if (!mounted) return;
      const fresh = !model || model.id !== m.id;
      model = m;
      titleEl.innerHTML = m.title || "";
      titleEl.hidden = !m.title;
      if (!quiet || bodyEl.innerHTML !== m.html) bodyEl.innerHTML = m.html;
      countEl.textContent = m.progress;
      dotsEl.innerHTML = "";
      m.chapters.forEach((c) => {
        const li = make("li", "atlas-tour-dot", { "data-state": c.state, title: c.title });
        li.appendChild(make("span", "atlas-tour-sr")).textContent = c.title;
        dotsEl.appendChild(li);
      });
      dotsEl.hidden = !m.chapters.length;
      const watch = m.mode === "watch";
      btn.back.textContent = h.label("back"); btn.back.hidden = !m.canBack;
      btn.skip.textContent = h.label("skip"); btn.skip.hidden = watch || m.last;
      btn.doIt.textContent = h.label("doIt"); btn.doIt.hidden = !m.canDoIt;
      btn.next.textContent = watch ? h.label("stop") : h.label(m.last ? "done" : "next");
      btn.next.hidden = !(watch || m.reading);
      const primary = watch ? null : m.reading ? btn.next : m.canDoIt ? btn.doIt : null;
      [btn.doIt, btn.next].forEach((b) => b.classList.toggle("atlas-tour-primary", b === primary));
      busy(false);
      if (fresh) {
        setTargets(m.targets, m.padding, m.radius, m.selectors);
        bubble.classList.remove("is-in"); void bubble.offsetWidth; bubble.classList.add("is-in");
        if (primary && !quiet) primary.focus({ preventScroll: true }); else if (!quiet) bubble.focus({ preventScroll: true });
        scrollPending = true;
      }
    }

    let selectors = [];
    function setTargets(els, pad, radius, sels) {
      targets = els || []; selectors = sels || [];
      rootEl.dataset.pad = pad; rootEl.dataset.radius = radius;
      if (!targets.length) {
        // no target (intro card): every hole closes into its centre
        holes.forEach((ho) => { ho.dying = true; ho.goal = { x: ho.x + ho.w / 2, y: ho.y + ho.h / 2, w: 0, h: 0, r: 0 }; });
      }
    }

    function syncHoles(goals, radius) {
      const live = holes.filter((ho) => !ho.dying);
      const from = unionRect(live) || null;
      goals.forEach((g, i) => {
        const goal = { x: g.x, y: g.y, w: g.w, h: g.h, r: Math.min(radius, g.w / 2, g.h / 2) };
        let ho = live[i];
        if (!ho) {
          const start = from ? { x: from.x, y: from.y, w: from.w, h: from.h, r: goal.r } : goal;
          ho = Object.assign({ goal, dying: false, mask: svgEl("rect"), glow: svgEl("rect") }, start);
          maskG.appendChild(ho.mask); glowG.appendChild(ho.glow); holes.push(ho);
        }
        ho.goal = goal;
      });
      live.slice(goals.length).forEach((ho) => {
        const c = goals[0] || ho;
        ho.dying = true; ho.goal = { x: c.x + c.w / 2, y: c.y + c.h / 2, w: 0, h: 0, r: 0 };
      });
    }

    function frame(t) {
      frameH = null;
      if (!mounted) return;
      const dt = Math.min(0.05, lastT ? (t - lastT) / 1000 : 0.016);
      lastT = t;
      const v = vp(), pad = +rootEl.dataset.pad || 0, radius = +rootEl.dataset.radius || 0;
      // read everything first, write after: one layout per frame
      if (selectors.length && targets.some((e) => !e.isConnected)) { // re-rendered by the app: find the new elements
        const again = selectors.map((s) => doc.querySelector(s)).filter(Boolean);
        if (again.length) targets = again;
      }
      const rects = targets.filter((e) => e.isConnected).map((e) => toRect(e.getBoundingClientRect())).filter((r) => r.w > 0 || r.h > 0);
      const bw = bubble.offsetWidth, bh = bubble.offsetHeight;
      const goals = mergeRects(rects.map((r) => padRect(r, pad)), 2);
      if (goals.length) syncHoles(goals, radius); // targets hidden for a moment (tab switch): hold the hole where it is
      const still = reduced();
      holes = holes.filter((ho) => {
        const done = still ? (HOLE_KEYS.forEach((k) => { ho[k] = ho.goal[k]; }), true) : stepHole(ho, ho.goal, dt);
        if (ho.dying && (done || still)) { ho.mask.remove(); ho.glow.remove(); return false; }
        return true;
      });
      holes.forEach((ho) => {
        const a = { x: ho.x.toFixed(1), y: ho.y.toFixed(1), width: Math.max(0, ho.w).toFixed(1), height: Math.max(0, ho.h).toFixed(1), rx: Math.max(0, ho.r).toFixed(1) };
        Object.keys(a).forEach((k) => { ho.mask.setAttribute(k, a[k]); ho.glow.setAttribute(k, a[k]); });
      });
      const open = mode === "watch" ? [] : holes.filter((ho) => !ho.dying).map((ho) => rect(ho.x, ho.y, ho.w, ho.h));
      const clip = `path(evenodd, "${holePath(open, v.w, v.h)}")`;
      if (clip !== lastClip) { blocker.style.clipPath = clip; lastClip = clip; }
      placeNow(goals, rects.length ? padRect(rects[0], pad) : null, v, bw, bh);
      if (scrollPending && bh) { scrollPending = false; revealTarget(goals, v, bh); }
      runTweens(t);
      loop();
    }
    function loop() { if (mounted && frameH == null && !pausedAt) frameH = root.requestAnimationFrame(frame); }

    const overlapArea = (a, b) => Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
    // the bubble points at the first target (with several targets the union may be empty space between them)
    function placeNow(goals, anchor, v, bw, bh) {
      let live = holes.filter((ho) => !ho.dying);
      const final = anchor || (targets.length ? unionRect(live) : null);
      if (anchor && live.length > 1) {
        const best = live.slice().sort((a, b) => overlapArea(b.goal, anchor) - overlapArea(a.goal, anchor))[0];
        live = [best];
      }
      const pref = model && model.side ? [model.side, "right", "left", "bottom", "top"] : undefined;
      const choice = placeBubble(final, { w: bw, h: bh }, v, { prefer: pref });
      // side from the final target (stable), position from the animated hole (follows the spring and scrolling)
      const pos = choice.side === "sheet" || choice.side === "center" || choice.side === "inside" || !live.length ? choice
        : placeBubble(unionRect(live), { w: bw, h: bh }, v, { side: choice.side });
      const key = `${choice.side}|${Math.round(pos.x)}|${Math.round(pos.y)}|${Math.round(pos.arrow || 0)}`;
      if (key === lastBubble) return;
      lastBubble = key;
      bubble.dataset.side = choice.side;
      bubble.style.transform = choice.side === "sheet" ? "" : `translate3d(${Math.round(pos.x)}px,${Math.round(pos.y)}px,0)`;
      arrowEl.hidden = pos.arrow == null;
      if (pos.arrow != null) {
        arrowEl.style.transform = choice.side === "left" || choice.side === "right" ? `translate3d(0,${Math.round(pos.arrow)}px,0) rotate(45deg)` : `translate3d(${Math.round(pos.arrow)}px,0,0) rotate(45deg)`;
      }
    }
    // bring the target into view; on phones keep it above the bottom sheet
    function revealTarget(goals, v, bh) {
      const u = unionRect(goals);
      if (!u) return;
      const bottom = sheet() ? v.h - bh - 12 : v.h - 12, d = scrollDelta(u, 12, bottom);
      if (Math.abs(d) > 2) win.scrollBy({ top: d, behavior: reduced() ? "auto" : "smooth" });
    }

    function nudge() {
      if (!glowG) return;
      glowG.classList.remove("is-nudge"); glowG.getBoundingClientRect(); glowG.classList.add("is-nudge");
    }

    // --- tweens driven by the same frame loop
    function tween(dur, fn) {
      return new Promise((res) => {
        if (!(dur > 0)) { fn(1); res(); return; }
        tweens.push({ start: null, dur, fn, res });
        loop();
      });
    }
    function runTweens(t) {
      if (!tweens.length) return;
      tweens = tweens.filter((tw) => {
        if (tw.start == null) tw.start = t;
        const p = Math.min(1, (t - tw.start) / tw.dur);
        tw.fn(p);
        if (p >= 1) { tw.res(); return false; }
        return true;
      });
    }
    function setGhost(p) {
      ghostPos = p;
      ghost.style.transform = `translate3d(${Math.round(p.x)}px,${Math.round(p.y)}px,0)`;
    }
    function ghostOn() {
      if (ghostIdle) { root.clearTimeout(ghostIdle); ghostIdle = null; }
      ghost.classList.add("is-on");
    }
    function ghostRest() {
      if (ghostIdle) root.clearTimeout(ghostIdle);
      ghostIdle = root.setTimeout(() => { if (ghost) ghost.classList.remove("is-on"); }, 1600);
    }
    function ripple(p) {
      const r = make("span", "atlas-tour-ripple");
      r.style.transform = `translate3d(${Math.round(p.x)}px,${Math.round(p.y)}px,0)`;
      r.appendChild(make("i"));
      rootEl.appendChild(r);
      root.setTimeout(() => r.remove(), 750);
    }
    function chip(el, txt) {
      if (!txt) return;
      const c = make("span", "atlas-tour-chip", { "aria-hidden": "true" }), r = el.getBoundingClientRect();
      c.textContent = txt;
      c.style.transform = `translate3d(${Math.round(Math.min(r.left, win.innerWidth - 200))}px,${Math.round(r.bottom + 6)}px,0)`;
      rootEl.appendChild(c);
      root.setTimeout(() => c.classList.add("is-out"), 1400);
      root.setTimeout(() => c.remove(), 1800);
    }
    function flash(el) {
      el.classList.remove("atlas-tour-flash"); void el.offsetWidth; el.classList.add("atlas-tour-flash");
      root.setTimeout(() => el.classList.remove("atlas-tour-flash"), 900);
    }
    const ptIn = (el, f) => fracPoint(toRect(el.getBoundingClientRect()), f);
    function flyTo(getPoint, tok) {
      const to0 = getPoint();
      if (!ghostPos) {
        const b = bubble.getBoundingClientRect();
        setGhost(b.width ? { x: b.left + b.width / 2, y: b.top + 20 } : { x: win.innerWidth / 2, y: win.innerHeight - 40 });
      }
      ghostOn();
      const from = ghostPos, dist = Math.hypot(to0.x - from.x, to0.y - from.y);
      if (reduced() || dist < 2) { setGhost(to0); return Promise.resolve(); }
      return tween(flightDuration(dist), (p) => {
        if (tok !== ghostTok) return;
        const to = getPoint();
        setGhost(bezierPoint(from, arcControl(from, to), to, easeInOut(p)));
      });
    }
    const wait = (ms) => new Promise((r) => root.setTimeout(r, ms));
    async function press(down) {
      ghost.classList.add("is-down");
      ripple(ghostPos);
      await wait(160);
      if (!down) ghost.classList.remove("is-down");
    }
    function drawTrail() { trail.setAttribute("d", trailPts.length ? "M" + trailPts.map((p) => `${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join("L") : ""); }
    function moveAlong(getPts, dur, tok, onPoint, withTrail) {
      trailPts = []; trail.classList.remove("is-out");
      let lastCall = -1;
      const dd = reduced() ? 0 : dur;
      return tween(dd, (p) => {
        if (tok !== ghostTok) return;
        const pt = polylinePoint(getPts(), easeInOut(p));
        setGhost(pt);
        if (withTrail) { trailPts.push(pt); drawTrail(); }
        if (onPoint && (p - lastCall > 0.08 || p === 1)) { lastCall = p; onPoint(pt); }
      });
    }

    // the ghost shows (and with real=true performs) the step's gesture
    async function perform(step, el, opt) {
      const tok = ++ghostTok, g = step.ghost, v = g.value || {}, gesture = g.gesture || "click";
      const alive = () => tok === ghostTok && mounted;
      if (!el || !el.isConnected) return;
      try {
        if (gesture === "drag") {
          // value may be a function of the target box, re-read every frame (e.g. screen points of a place on a moving globe)
          const spec = () => { const s = typeof g.value === "function" ? g.value(toRect(el.getBoundingClientRect())) || {} : v; return [g.from || s.from || [0.3, 0.3], g.to2 || s.to || [0.7, 0.7]]; };
          const P = (f) => f.x != null ? f : ptIn(el, f);
          await flyTo(() => P(spec()[0]), tok); if (!alive()) return;
          await press(true); if (!alive()) return;
          const a = P(spec()[0]);
          await moveAlong(() => [P(spec()[0]), P(spec()[1])], 950, tok, null, true); if (!alive()) return;
          ghost.classList.remove("is-down");
          trail.classList.add("is-out");
          if (opt.real) await opt.act({ from: a, to: P(spec()[1]), points: [a, P(spec()[1])] });
        } else if (gesture === "path" || gesture === "hover") {
          const fr = gesture === "hover" ? [g.at || (Array.isArray(v) && typeof v[0] === "number" ? v : [0.5, 0.5])]
            : (typeof g.points === "function" || typeof v === "function" ? null : g.points || v);
          const pts = () => {
            if (fr) return fr.map((f) => ptIn(el, f));
            const r = toRect(el.getBoundingClientRect());
            return (g.points || v)(r).map((p) => p.x != null ? p : fracPoint(r, p));
          };
          await flyTo(() => pts()[0], tok); if (!alive()) return;
          const call = opt.real ? (pt) => opt.act({ point: pt, points: pts() }) : null;
          if (gesture === "path") await moveAlong(pts, 1500, tok, call, false);
          else {
            if (call) call(pts()[0]);
            const c = pts()[0];
            await moveAlong(() => [c, { x: c.x + 10, y: c.y + 6 }, { x: c.x - 6, y: c.y + 3 }, c], 700, tok, call, false);
          }
        } else {
          await flyTo(() => ptIn(el, g.at || [0.5, 0.5]), tok); if (!alive()) return;
          await press(false); if (!alive()) return;
          if (gesture === "select") {
            flash(el);
            if (opt.real) await opt.act();
            const option = el.options ? Array.from(el.options).find((x) => x.value === String(opt.value)) : null;
            chip(el, option ? option.textContent.trim() : "");
          } else if (opt.real) await opt.act();
        }
        if (alive()) await wait(220);
      } finally {
        if (ghost && tok === ghostTok) { ghost.classList.remove("is-down"); ghostRest(); }
      }
    }
    function cancelGhost() {
      ghostTok++;
      tweens.forEach((tw) => tw.res()); tweens = [];
      if (ghost) ghost.classList.remove("is-down");
      if (trail) { trail.classList.add("is-out"); }
    }
    function pause() {
      pausedAt = root.performance.now();
      if (frameH != null) root.cancelAnimationFrame(frameH);
      frameH = null;
    }
    function resume() {
      if (!pausedAt) return;
      const gap = root.performance.now() - pausedAt;
      pausedAt = 0; lastT = 0;
      tweens.forEach((tw) => { if (tw.start != null) tw.start += gap; });
      loop();
    }
    return { mount, unmount, show, busy, perform, cancelGhost, pause, resume, nudge };
  }

  // ------------------------------------------------------------------ case board: What / Where / How much / Significant?
  function createCaseBoard(options) {
    const o = options || {}, doc = root.document;
    const lab = (k) => typeof o.labels === "function" ? (o.labels(k) || DEFAULT_LABELS[k]) : Object.assign({}, DEFAULT_LABELS, o.labels || {})[k];
    const slots = o.slots || ["what", "where", "howMuch", "significant"];
    const el = doc.createElement("section");
    el.className = "atlas-tour-board";
    el.setAttribute("aria-label", lab("board"));
    const list = doc.createElement("ol");
    const items = {};
    slots.forEach((id) => {
      const li = doc.createElement("li");
      li.className = "atlas-tour-slot"; li.dataset.slot = id; li.dataset.on = "0";
      li.innerHTML = `<svg class="atlas-tour-ic" aria-hidden="true"><use href="${o.iconHref || "/static/icons.svg"}#i-check"/></svg><span class="atlas-tour-slot-name"></span><span class="atlas-tour-slot-value"></span>`;
      li.querySelector(".atlas-tour-slot-name").textContent = lab(id);
      list.appendChild(li); items[id] = li;
    });
    const live = doc.createElement("span");
    live.className = "atlas-tour-sr"; live.setAttribute("aria-live", "polite");
    el.append(list, live);
    (o.mount || doc.body).appendChild(el);
    if (o.hidden) el.hidden = true;
    return {
      el,
      light(slot, value) {
        const li = items[slot];
        if (!li) return false;
        li.dataset.on = "1";
        li.querySelector(".atlas-tour-slot-value").textContent = value == null ? "" : String(value);
        li.classList.remove("is-new"); void li.offsetWidth; li.classList.add("is-new");
        live.textContent = lab(slot) + (value == null ? "" : " – " + value);
        return true;
      },
      isLit: (slot) => !!items[slot] && items[slot].dataset.on === "1",
      reset() { Object.keys(items).forEach((k) => { items[k].dataset.on = "0"; items[k].querySelector(".atlas-tour-slot-value").textContent = ""; }); live.textContent = ""; },
      show() { el.hidden = false; },
      hide() { el.hidden = true; },
      remove() { el.remove(); },
    };
  }

  root.AtlasTourEngine = {
    version: 1,
    create: createTour,
    createCaseBoard,
    parseTourParam,
    labels: DEFAULT_LABELS,
    actions: DEFAULT_ACTIONS,
    _pure: { unionRect, mergeRects, padRect, fracPoint, placeBubble, springStep, stepHole, lerpHole, holePath, flightDuration,
      arcControl, bezierPoint, easeInOut, polylinePoint, scrollDelta, parseTourParam, createStore, SPRING },
  };
})(typeof window !== "undefined" ? window : this);
