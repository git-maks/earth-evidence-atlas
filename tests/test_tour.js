/* Tour engine logic without a browser: geometry, spring, step runner on a fake clock, saved state. Run via pytest or `node tests/test_tour.js`. */
"use strict";
const assert = require("assert"), fs = require("fs"), vm = require("vm");
const source = fs.readFileSync("web/tour.js", "utf8");
const context = { URLSearchParams, console: { info() {} } };
vm.createContext(context);
vm.runInContext(source, context);
const E = context.AtlasTourEngine, P = E._pure, J = (x) => JSON.parse(JSON.stringify(x));

// ------------------------------------------------------------ pure helpers
const vp = { w: 1440, h: 900 }, size = { w: 340, h: 180 };
(function placement() {
  let r = P.placeBubble({ x: 100, y: 300, w: 200, h: 100 }, size, vp);
  assert.strictEqual(r.side, "right"); assert.strictEqual(r.x, 314); assert(r.fits);
  r = P.placeBubble({ x: 1200, y: 300, w: 200, h: 100 }, size, vp);
  assert.strictEqual(r.side, "left", "flips when the right side has no room"); assert.strictEqual(r.x, 1200 - 14 - 340);
  r = P.placeBubble({ x: 20, y: 40, w: 1400, h: 200 }, size, vp);
  assert.strictEqual(r.side, "bottom"); assert.strictEqual(r.y, 254);
  r = P.placeBubble({ x: 20, y: 600, w: 1400, h: 280 }, size, vp);
  assert.strictEqual(r.side, "top");
  r = P.placeBubble({ x: 0, y: 0, w: 1440, h: 900 }, size, vp);
  assert.strictEqual(r.side, "inside"); assert(!r.fits); assert(r.x + size.w <= vp.w && r.y + size.h <= vp.h);
  r = P.placeBubble({ x: 100, y: 5, w: 100, h: 20 }, size, vp);
  assert.strictEqual(r.side, "right"); assert.strictEqual(r.y, 12, "shifted to stay on screen"); assert.strictEqual(r.arrow, 16);
  r = P.placeBubble({ x: 100, y: 300, w: 200, h: 100 }, size, vp, { prefer: ["bottom", "right"] });
  assert.strictEqual(r.side, "bottom");
  r = P.placeBubble({ x: 1300, y: 300, w: 100, h: 100 }, size, vp, { side: "right" });
  assert.strictEqual(r.side, "right"); assert(r.x <= vp.w - 12 - size.w, "forced side is clamped");
  assert.strictEqual(P.placeBubble({ x: 10, y: 10, w: 50, h: 50 }, size, { w: 390, h: 800 }).side, "sheet");
  assert.strictEqual(P.placeBubble({ x: 10, y: 10, w: 50, h: 50 }, size, { w: 900, h: 800 }).side, "sheet");
  r = P.placeBubble(null, size, vp);
  assert.strictEqual(r.side, "center"); assert.strictEqual(r.x, (1440 - 340) / 2);
})();

(function rects() {
  const m = P.mergeRects([{ x: 0, y: 0, w: 10, h: 10 }, { x: 5, y: 5, w: 10, h: 10 }, { x: 100, y: 0, w: 10, h: 10 }, { x: 0, y: 0, w: 0, h: 5 }]);
  assert.strictEqual(m.length, 2);
  assert.deepStrictEqual(JSON.parse(JSON.stringify(m[0])), { x: 0, y: 0, w: 15, h: 15 });
  assert.strictEqual(P.mergeRects([{ x: 0, y: 0, w: 10, h: 10 }, { x: 11, y: 0, w: 5, h: 5 }], 2).length, 1, "nearly touching rectangles merge");
  assert.strictEqual(P.unionRect([]), null);
  const path = P.holePath([{ x: 1, y: 2, w: 3, h: 4 }, { x: 10, y: 10, w: 5, h: 5 }], 100, 50);
  assert.strictEqual(path, "M0 0H100V50H0ZM1 2h3v4h-3ZM10 10h5v5h-5Z");
  assert.deepStrictEqual(JSON.parse(JSON.stringify(P.padRect({ x: 10, y: 10, w: 10, h: 10 }, 4))), { x: 6, y: 6, w: 18, h: 18 });
})();

(function spring() {
  const a = { x: 0, y: 0, w: 100, h: 40, r: 10 }, b = { x: 400, y: 300, w: 200, h: 80, r: 6 };
  const hole = Object.assign({}, a);
  let t = 0, maxX = 0, settledAt = null;
  while (t < 2) {
    const done = P.stepHole(hole, b, 1 / 60); t += 1 / 60; maxX = Math.max(maxX, hole.x);
    if (Math.abs(t - 0.45) < 1 / 120) assert(Math.abs(hole.x - b.x) < 0.03 * 400, `x at 450 ms: ${hole.x}`);
    if (done && settledAt === null) settledAt = t;
  }
  assert(maxX - b.x < 0.05 * 400, `overshoot ${maxX - b.x}`);
  assert(settledAt !== null && settledAt < 0.9, `settled at ${settledAt}`);
  assert.deepStrictEqual(["x", "y", "w", "h", "r"].map((k) => hole[k]), [400, 300, 200, 80, 6]);
  // a long frame (tab in background) must not explode
  const h2 = Object.assign({}, a); P.stepHole(h2, b, 0.05);
  assert(h2.x > 0 && h2.x < 420);
  assert.deepStrictEqual(JSON.parse(JSON.stringify(P.lerpHole(a, b, 0.5))), { x: 200, y: 150, w: 150, h: 60, r: 8 });
})();

(function ghostPath() {
  assert.strictEqual(P.flightDuration(0), 500);
  assert.strictEqual(P.flightDuration(5000), 900);
  assert(P.flightDuration(300) > P.flightDuration(100));
  const a = { x: 0, y: 100 }, b = { x: 200, y: 100 }, c = P.arcControl(a, b);
  assert(c.y < 100, "the arc bows upwards");
  assert.deepStrictEqual(JSON.parse(JSON.stringify(P.bezierPoint(a, c, b, 0))), a);
  assert.deepStrictEqual(JSON.parse(JSON.stringify(P.bezierPoint(a, c, b, 1))), b);
  assert.strictEqual(P.easeInOut(0), 0); assert.strictEqual(P.easeInOut(1), 1); assert.strictEqual(P.easeInOut(0.5), 0.5);
  const pts = [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }];
  assert.deepStrictEqual(JSON.parse(JSON.stringify(P.polylinePoint(pts, 0.5))), { x: 10, y: 0 });
  assert.deepStrictEqual(JSON.parse(JSON.stringify(P.polylinePoint(pts, 1))), { x: 10, y: 10 });
  assert.strictEqual(P.scrollDelta({ x: 0, y: 100, w: 10, h: 50 }, 12, 500), 0);
  assert.strictEqual(P.scrollDelta({ x: 0, y: 700, w: 10, h: 50 }, 12, 500), 250);
  assert.strictEqual(P.scrollDelta({ x: 0, y: -80, w: 10, h: 50 }, 12, 500), -92);
  assert.strictEqual(P.scrollDelta({ x: 0, y: 300, w: 10, h: 900 }, 12, 500), 288, "too tall: align its top");
})();

(function params() {
  assert.strictEqual(E.parseTourParam(""), null);
  assert.strictEqual(E.parseTourParam("?lang=pl"), null);
  assert.deepStrictEqual(JSON.parse(JSON.stringify(E.parseTourParam("?tour=0"))), { disabled: true, mode: "free", tour: null });
  assert.deepStrictEqual(JSON.parse(JSON.stringify(E.parseTourParam("?tour=watch"))), { disabled: false, mode: "watch", tour: null });
  assert.deepStrictEqual(JSON.parse(JSON.stringify(E.parseTourParam("?lang=pl&tour=case1"))), { disabled: false, mode: "guided", tour: "case1" });
})();

function memoryStorage() {
  const box = {};
  return { box, getItem: (k) => (k in box ? box[k] : null), setItem: (k, v) => { box[k] = String(v); }, removeItem: (k) => { delete box[k]; } };
}
(function storage() {
  const s = memoryStorage(), store = P.createStore("k", s);
  assert.strictEqual(store.read().status, "new");
  store.write(Object.assign(store.blank(), { step: "b", done: ["a"] }));
  assert.strictEqual(store.read().step, "b");
  s.box.k = "{broken"; assert.strictEqual(store.read().status, "new");
  const throwing = { getItem() { throw Error("denied"); }, setItem() { throw Error("denied"); }, removeItem() { throw Error("denied"); } };
  const t2 = P.createStore("k", throwing);
  assert.strictEqual(t2.read().status, "new"); t2.write({ v: 1 }); t2.clear();
})();

// ------------------------------------------------------------ step runner on a fake clock
const flush = () => new Promise((r) => setImmediate(r));
function fakeEnv() {
  let now = 0, seq = 0, timers = [], listeners = [];
  const env = {
    now: () => now,
    setTimeout(f, ms) { const id = ++seq; timers.push({ id, at: now + ms, f }); return id; },
    clearTimeout(id) { timers = timers.filter((t) => t.id !== id); },
    frame(f) { return env.setTimeout(() => f(now), 16); },
    cancelFrame(id) { env.clearTimeout(id); },
    elements: {},
    query(s) { return typeof s === "string" ? env.elements[s] || null : s; },
    measure(el) { return el && el.visible !== false ? Object.assign({}, el.rect) : null; },
    listen(target, type, fn) { const l = { target, type, fn }; listeners.push(l); return () => { listeners = listeners.filter((x) => x !== l); }; },
    fire(target, type, detail) { listeners.filter((l) => l.target === target && l.type === type).forEach((l) => l.fn({ type, detail, target })); },
    count: (type) => listeners.filter((l) => l.type === type).length,
    window: {},
    document: null,
    async tick(ms) {
      const end = now + ms;
      for (;;) {
        await flush();
        timers.sort((a, b) => a.at - b.at || a.id - b.id);
        const t = timers[0];
        if (!t || t.at > end) break;
        timers.shift(); now = t.at; t.f();
      }
      now = end;
      await flush();
    },
  };
  return env;
}
const el = (x, y) => ({ rect: { x, y, w: 80, h: 30 }, visible: true });
function setup(steps, extra) {
  const env = fakeEnv(), storage = memoryStorage(), logs = [], events = [], clicks = [];
  ["#a", "#b", "#c", "#d"].forEach((s, i) => { env.elements[s] = el(10 + i * 100, 10); });
  const tour = E.create(Object.assign({
    steps, env, storage, ui: false, log: function () { logs.push(Array.prototype.slice.call(arguments).join(" ")); },
    actions: { click: (e) => { clicks.push(e); env.fire(e, "click"); }, setValue: (e, v) => { e.value = v; env.fire(e, "change"); } },
    t: (k, p) => `${k}:${JSON.stringify(p)}`,
  }, extra || {}));
  ["step", "complete", "skip", "end"].forEach((n) => tour.on(n, (d) => events.push(n + ":" + (d.step ? d.step.id : d.reason))));
  return { env, storage, logs, events, clicks, tour };
}

(async function runner() {
  // order and transitions: reading step → event step → predicate step → end
  {
    let flag = false;
    const steps = [
      { id: "one", targets: ["#a"], text: "tour.one" },
      { id: "two", targets: ["#b"], waitFor: { event: "atlas:var", test: (v) => v === "lst_day" } },
      { id: "three", targets: ["#c"], waitFor: { predicate: () => flag } },
    ];
    const { env, events, tour, storage } = setup(steps);
    assert.strictEqual(tour.start({ mode: "guided" }), true);
    await env.tick(100);
    assert.strictEqual(tour.index, 0, "waits for Next on a reading step");
    tour.next(); await env.tick(100);
    assert.strictEqual(tour.index, 1);
    env.fire(env.window, "atlas:var", "ndvi"); await env.tick(50);
    assert.strictEqual(tour.index, 1, "test() rejects the wrong value");
    env.fire(env.window, "atlas:var", "lst_day"); await env.tick(100);
    assert.strictEqual(tour.index, 2);
    await env.tick(5000);
    assert.strictEqual(tour.index, 2, "user wait in guided mode has no time limit");
    flag = true; await env.tick(100);
    assert.strictEqual(tour.active, false);
    assert.deepStrictEqual(events, ["step:one", "complete:one", "step:two", "complete:two", "step:three", "complete:three", "end:done"]);
    const saved = JSON.parse(storage.box["atlas.tour.v1"]);
    assert.strictEqual(saved.status, "done"); assert.deepStrictEqual(saved.done, ["one", "two", "three"]);
    assert.strictEqual(env.count("atlas:var"), 0, "listeners are removed");
  }
  // missing target: logged, skipped in the direction of travel
  {
    const steps = [{ id: "a", targets: ["#a"] }, { id: "gone", targets: ["#nope"] }, { id: "c", targets: ["#c"] }];
    const { env, logs, events, tour } = setup(steps, { readyTimeout: 8000 });
    tour.start();
    await env.tick(100); tour.next();
    await env.tick(7900);
    assert.strictEqual(tour.index, 1, "keeps waiting up to the limit");
    await env.tick(200);
    assert.strictEqual(tour.index, 2, "skipped after 8 s");
    assert(logs.some((l) => l.includes("no target") && l.includes("gone")));
    assert(events.includes("skip:gone"));
    tour.back(); await env.tick(8200);
    assert.strictEqual(tour.index, 0, "Back over a missing step keeps going back");
    assert.deepStrictEqual(J(tour.state.skipped), ["gone"]);
    tour.stop();
    assert.strictEqual(tour.state.status, "dismissed");
  }
  // waitReady: element appears late and moves for a while; ready only after 2 stable frames
  {
    const { env, tour } = setup([{ id: "late", targets: ["#late"] }]);
    const late = el(0, 0); late.visible = false; env.elements["#late"] = late;
    let ready = null;
    tour.waitReady("#late", 2000).then((x) => { ready = x; });
    await env.tick(300); assert.strictEqual(ready, null);
    late.visible = true;
    for (let i = 0; i < 10; i++) { late.rect.y += 5; await env.tick(16); }
    assert.strictEqual(ready, null, "still moving");
    await env.tick(16 * 4);
    assert.strictEqual(ready, late);
    let none = 0;
    tour.waitReady("#never", 500).then((x) => { none = x; });
    await env.tick(520); assert.strictEqual(none, null);
  }
  // Do it for me: real action, then an 8 s limit on the expected event
  {
    const steps = [{ id: "go", targets: ["#a"], ghost: { gesture: "click" }, waitFor: { event: "globe:result" } }, { id: "after", targets: ["#b"] }];
    const { env, clicks, logs, tour, events } = setup(steps);
    tour.start(); await env.tick(100);
    tour.doIt(); await env.tick(10);
    assert.strictEqual(clicks.length, 1); assert.strictEqual(clicks[0], env.elements["#a"]);
    await env.tick(7900); assert.strictEqual(tour.index, 0);
    await env.tick(200); assert.strictEqual(tour.index, 1, "moves on after the timeout");
    assert(logs.some((l) => l.includes("timed out")));
    assert(events.includes("complete:go"));
  }
  // pause (hidden tab) freezes the limits
  {
    const steps = [{ id: "go", targets: ["#a"], ghost: { gesture: "click" }, waitFor: { event: "never" } }, { id: "b", targets: ["#b"] }];
    const { env, tour } = setup(steps);
    tour.start(); await env.tick(100);
    tour.doIt(); await env.tick(4000);
    tour.pause(); await env.tick(20000);
    assert.strictEqual(tour.index, 0, "no progress while hidden");
    tour.resume(); await env.tick(3900);
    assert.strictEqual(tour.index, 0);
    await env.tick(200);
    assert.strictEqual(tour.index, 1);
  }
  // select gesture uses setValue with a value that may come from data
  {
    const sel = el(0, 0);
    const steps = [{ id: "var", targets: ["#sel"], ghost: { gesture: "select", value: (ctx) => ctx.data.v }, waitFor: { event: "change", on: "#sel", test: (d, e) => e.target.value === "lst_day" } }];
    const { env, tour } = setup(steps);
    env.elements["#sel"] = sel;
    tour.set({ v: "lst_day" });
    tour.start(); await env.tick(100);
    tour.doIt(); await env.tick(100);
    assert.strictEqual(sel.value, "lst_day");
    assert.strictEqual(tour.active, false);
  }
  // Watch mode: the ghost does everything, nothing is saved, same order every time
  {
    const steps = [
      { id: "intro" },
      { id: "click", targets: ["#a"], ghost: { gesture: "click" }, waitFor: { event: "click", on: "#a" } },
      { id: "read", targets: ["#b"] },
    ];
    const runs = [];
    for (let r = 0; r < 2; r++) {
      const { env, storage, events, clicks, tour } = setup(steps, { dwell: 1000 });
      tour.start({ mode: "watch" });
      await env.tick(10000);
      assert.strictEqual(tour.active, false);
      assert.strictEqual(clicks.length, 1);
      assert.strictEqual(storage.box["atlas.tour.v1"], undefined, "watch mode leaves saved progress alone");
      runs.push({ events: events.join(), at: env.now() });
    }
    assert.strictEqual(runs[0].events, runs[1].events);
  }
  // resume from the saved step; Free mode does nothing
  {
    const steps = [{ id: "a", targets: ["#a"] }, { id: "b", targets: ["#b"] }, { id: "c", targets: ["#c"] }];
    const first = setup(steps);
    first.tour.start(); await first.env.tick(100); first.tour.next(); await first.env.tick(100);
    assert.strictEqual(first.tour.index, 1);
    first.tour.stop();
    const again = E.create({ steps, env: first.env, storage: first.storage, ui: false, log() {} });
    again.start({ resume: true }); await first.env.tick(100);
    assert.strictEqual(again.index, 1);
    assert.deepStrictEqual(J(again.state.done), ["a"], "progress survives a resume");
    again.stop();
    const fresh = E.create({ steps, env: first.env, storage: first.storage, ui: false, log() {} });
    assert.strictEqual(fresh.start({ mode: "free" }), false);
    assert.strictEqual(fresh.active, false);
  }
  // Back onto a predicate step that is already satisfied waits for a real change instead of bouncing forward
  {
    let flag = false;
    const steps = [{ id: "p", targets: ["#a"], waitFor: { predicate: () => flag } }, { id: "q", targets: ["#b"] }];
    const { env, tour } = setup(steps);
    tour.start(); await env.tick(100);
    flag = true; await env.tick(100);
    assert.strictEqual(tour.index, 1);
    tour.back(); await env.tick(500);
    assert.strictEqual(tour.index, 0);
    flag = false; await env.tick(50); flag = true; await env.tick(50);
    assert.strictEqual(tour.index, 1);
  }
  // Skip records the step; texts go through the injected t() with data
  {
    const steps = [{ id: "a", targets: ["#a"], waitFor: { event: "x" } }, { id: "b", targets: ["#b"] }];
    const shown = [];
    const fakeUi = { mount() {}, unmount() {}, busy() {}, cancelGhost() {}, pause() {}, resume() {}, show(m) { shown.push(m); }, perform() { return Promise.resolve(); } };
    const { env, tour } = setup(steps, { ui: fakeUi });
    steps[1].text = "tour.rate";
    tour.set({ rate: "+0.3" });
    tour.start(); await env.tick(100);
    assert.strictEqual(shown[0].canDoIt, false); assert.strictEqual(shown[0].reading, false);
    tour.skip(); await env.tick(100);
    assert.deepStrictEqual(J(tour.state.skipped), ["a"]);
    assert.strictEqual(shown[shown.length - 1].html, 'tour.rate:{"rate":"+0.3"}');
    assert.strictEqual(shown[shown.length - 1].progress, "Step 2 of 2");
    assert.strictEqual(shown[shown.length - 1].last, true);
  }
  console.log("tour engine: all checks passed");
})().catch((e) => { console.error(e); process.exit(1); });
