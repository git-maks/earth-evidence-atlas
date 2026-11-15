/* A read-only brief backed by the same analyses as Detective. */
"use strict";

const Resilience = (() => {
  const variables = ["t2m", "lst_day", "precip", "soil_root"];
  const limits = ["exposure", "history", "water", "heat", "shared", "scale", "causes"];
  const seasons = { [ALL]: "calendar.allYear", "12,1,2": "calendar.seasons.djf.description",
    "3,4,5": "calendar.seasons.mam.description", "6,7,8": "calendar.seasons.jja.description",
    "9,10,11": "calendar.seasons.son.description" };
  let place = { region: "central_europe" }, selection = null, places = [];
  let months = ALL, start = null, end = null, report = null, request = null;
  let years = null, phase = "idle", closedOnPrint = [];
  let useExistingAnalyses = false, errorText = "loadError";
  const get = (name) => $(`#resilience-${name}`);
  const tr = (key, values) => t(`resilience.${key}`, values);
  const seasonValue = (value) => {
    if (!/^\d{1,2}(,\d{1,2})*$/.test(value || "")) return ALL;
    const sorted = [...new Set(value.split(",").map(Number))].sort((a, b) => a - b);
    if (sorted.some((m) => m < 1 || m > 12)) return ALL;
    return sorted.join(",") === "1,2,12" ? "12,1,2" : sorted.join(",");
  };
  const coordinates = (box) => box.map((n) => I18N.number(n, { maximumFractionDigits: 3 })).join(" / ");
  const placeKey = ({ region, bbox }) => JSON.stringify([region || null, bbox || null]);
  const placeName = ({ region, bbox }) => {
    if (bbox) return tr("selected", { coordinates: coordinates(bbox) });
    const entry = CAT.regions.find((r) => r.id === region);
    return entry ? entry.name : tr("unknownArea");
  };

  function populatePlaces() {
    const built = Object.entries(CAT.available).filter(([, present]) => present).map(([key]) => key.split("/")[1]);
    places = CAT.regions.filter((r) => r.custom ? AREAS.visible(r.id) && built.includes(r.id) :
      r.id !== "world" || variables.some((v) => available(v, r.id))).map((r) => ({ region: r.id }));
    const options = [...places, ...savedPlaces().map((p) => ({ bbox: p.bbox })), selection, place];
    places = [...new Map(options.filter(Boolean).map((area) => [placeKey(area), area])).values()];
    const select = get("area"), key = placeKey(place);
    select.replaceChildren(...places.map((area, index) => new Option(placeName(area), index, false, placeKey(area) === key)));
  }

  function populateYears() {
    const [first, last] = years || [];
    const options = (lo, hi, year) => Array.from({ length: hi - lo + 1 }, (_, i) => new Option(lo + i, lo + i, false, lo + i === year));
    get("start").replaceChildren(...(first ? options(first, last - MIN_PERIOD_SPAN, start) : []));
    get("end").replaceChildren(...(first ? options(first + MIN_PERIOD_SPAN, last, end) : []));
    get("start").disabled = get("end").disabled = !first;
  }

  function populateMonths() {
    const select = get("months");
    select.querySelectorAll("[data-extra]").forEach((option) => option.remove());
    if (!seasons[months]) {
      const option = new Option(months.split(",").map((m) => monthLabel(+m)).join(", "), months);
      option.dataset.extra = "";
      select.add(option);
    }
    select.value = months;
  }

  function params() {
    const query = new URLSearchParams({ months });
    if (place.region) query.set("region", place.region);
    if (place.bbox) query.set("bbox", place.bbox.join(","));
    if (start !== null) query.set("start", start);
    if (end !== null) query.set("end", end);
    return query;
  }

  function shareHash() { return "#view=resilience&" + params(); }

  async function loadFromAnalysis(query, options) {
    // Older servers already serve /api/analysis and the complete-year catalogue ranges.
    const region = query.get("region"), selected = CAT.regions.find((r) => r.id === region);
    if (region && !selected) throw Object.assign(new Error("Unknown region"), { detail: "unknown region" });
    const bbox = query.has("bbox") ? query.get("bbox").split(",").map(Number) : selected.bbox;
    const [w, s, e, n] = bbox;
    if (bbox.length !== 4 || !(w >= -180 && s >= -90 && e <= 180 && n <= 90 && w < e && s < n)) {
      throw Object.assign(new Error("Invalid area"), { detail: "invalid bbox" });
    }
    const containing = CAT.regions.filter((r) => coversPlace(r.bbox, bbox)).sort((a, b) => {
      const area = (r) => (r.bbox[2] - r.bbox[0]) * (r.bbox[3] - r.bbox[1]);
      return Number(b.id === region) - Number(a.id === region) || area(a) - area(b) || a.id.localeCompare(b.id, "en");
    });
    const catalog = CAT._raw || CAT;
    const cards = variables.map((variable) => {
      const source = containing.find((r) => available(variable, r.id));
      if (!source) return { variable, status: "missing_cube", data_region: null, years: null,
        result: null, verdict: null, cross_check: null, provenance: null };
      return { variable, data_region: source.id, years: catalog.variables.find((v) => v.id === variable).years,
        analysis_bbox: sameBox(source.bbox, bbox) ? null : bbox, status: "no_common_period",
        result: null, verdict: null, cross_check: null, provenance: null };
    });
    const records = cards.filter((card) => card.data_region);
    const first = Math.max(...records.map((card) => card.years[0]));
    const last = Math.min(...records.map((card) => card.years[1]));
    const hasPeriod = records.length > 0 && last - first >= MIN_PERIOD_SPAN;
    const start = hasPeriod ? Number(query.get("start") || first) : null;
    const end = hasPeriod ? Number(query.get("end") || last) : null;
    if (hasPeriod) {
      if (!(Number.isInteger(start) && Number.isInteger(end) && first <= start && start <= end - MIN_PERIOD_SPAN && end <= last)) {
        throw Object.assign(new Error("Outside common period"), { detail: "choose at least 5 years within the common period" });
      }
      await Promise.all(records.map(async (card) => {
        const analysisQuery = new URLSearchParams({ var: card.variable, region: card.data_region, start, end, months: query.get("months") });
        if (card.analysis_bbox) analysisQuery.set("bbox", card.analysis_bbox.join(","));
        const response = await api("analysis", analysisQuery, options);
        const data = response._raw || response;
        const { result, verdict, cross_check, provenance, trend_units, cells, answer } = data;
        Object.assign(card, { status: "ready", result, verdict, cross_check, provenance, trend_units, cells });
        if (cross_check) card.cross_check_source = catalog.variables.find((v) => v.id === cross_check.variable);
        if (answer && answer.source_url) card.advisory = { caveat: answer.caveat, source_url: answer.source_url };
      }));
    }
    return { region, area_name: selected ? selected.name : null, bbox, start, end,
      months: query.get("months").split(",").map(Number).sort((a, b) => a - b),
      years: hasPeriod ? [first, last] : null, cards, methods: catalog.methods,
      limitations: Object.fromEntries([...limits, "windows"].map((key) => [key, tr(`limits.${key}`)])) };
  }

  async function fetchReport(query, options) {
    if (!useExistingAnalyses) {
      try {
        return await api("resilience", query, options);
      } catch (error) {
        if (error.status !== 404 || error.detail !== "Not Found") throw error;
        useExistingAnalyses = true;
      }
    }
    return loadFromAnalysis(query, options);
  }

  function reportCsv() {
    const { cards, ...metadata } = report;
    const csvCell = (value) => `"${String(value == null ? "" : value).replace(/"/g, '""')}"`;
    const flatten = (record, prefix = "") => Object.entries(record).flatMap(([key, value]) => {
      const column = prefix + key;
      return value && typeof value === "object" && !Array.isArray(value) ?
        flatten(value, column + ".") : [[column, value]];
    });
    const csvRows = cards.map((card) => Object.fromEntries(flatten(card)));
    const columns = [...new Set(csvRows.flatMap(Object.keys))];
    return [
      "# Earth Evidence Atlas – Environmental Resilience Brief",
      ...Object.entries(metadata).map(([key, value]) => `# ${key}: ${JSON.stringify(value)}`),
      columns.join(","),
      ...csvRows.map((row) => columns.map((key) => {
        const value = row[key];
        return csvCell(value && typeof value === "object" ? JSON.stringify(value) : value);
      }).join(",")),
    ].join("\n");
  }

  function prepareExport(format) {
    const link = get(format);
    if (!useExistingAnalyses) {
      const query = params();
      query.set("format", format);
      link.href = `/api/resilience?${query}`;
      return;
    }
    const content = format === "csv" ? reportCsv() : JSON.stringify(report, null, 2);
    if (link.href.startsWith("blob:")) URL.revokeObjectURL(link.href);
    link.href = URL.createObjectURL(new Blob([content], { type: format === "csv" ? "text/csv" : "application/json" }));
    link.download = `atlas_resilience.${format}`;
  }

  function statusText() {
    if (phase === "loading") return t("common.loading");
    if (phase === "error") return tr(errorText);
    if (phase === "empty") return tr(report.cards.every((card) => card.status === "missing_cube") ? "noAreaData" : "noPeriod");
    return "";
  }

  function detectiveLink(card) {
    const params = { var: card.variable, region: card.data_region, start, end, months, bbox: card.analysis_bbox };
    const query = new URLSearchParams({ view: "atlas", var: params.var, region: params.region, start, end, months });
    if (params.bbox) query.set("bbox", params.bbox.join(","));
    const text = tr("openDetective");
    const id = `resilience-open-${card.variable}`;
    const name = tr(`variables.${card.variable}`);
    return { params, html: `<a class="ghost resilience-open" id="${id}" href="#${esc(query)}"
      aria-label="${esc(tr("openDetectiveLabel", { variable: name }))}">${esc(text)} ${ic("arrow")}</a>` };
  }

  const n = (value) => value == null ? t("common.notAvailable") : I18N.number(value);
  const slope = (value) => value > 0 ? "+" + n(value) : n(value);
  const interval = (low, high) => low == null || high == null ? t("common.notAvailable") : tr("interval", { low: n(low), high: n(high) });
  const metric = (label, value) => `<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`;

  function renderCheck(card) {
    const check = card.cross_check;
    if (!check) return card.variable === "soil_root" ? "" : `<p class="hint">${esc(tr("checkUnavailable"))}</p>`;
    const source = CAT.variables.find((v) => v.id === check.variable) || card.cross_check_source;
    const name = { gistemp: "GISTEMP", precip_gpcp: "GPCP", lst_day_aqua: "MODIS Aqua" }[check.variable] || source.product;
    const conclusion = t(`answers.crossCheck.conclusions.${check.agreement}`);
    const extra = check.sizes_differ && !["agree", "same_direction_different_size"].includes(check.agreement) ?
      ` ${t("answers.crossCheck.sizesDiffer")}` : "";
    return `<details class="resilience-check">
      <summary>${esc(name)} · ${esc(tr(`agreement.${check.agreement}`))}</summary>
      <p><a href="${esc(source.url)}" target="_blank" rel="noopener">${esc(source.product)}</a> · ${esc(source.resolution)}</p>
      <p>${esc(tr("checkValue", { start: check.start, end: check.end, slope: slope(check.slope),
        units: source.trend_units, range: interval(check.ci_low, check.ci_high), p: pStr(check.p) }))}</p>
      ${check.start !== start || check.end !== end ? `<p>${esc(tr("checkMain", { slope: slope(check.main_slope), units: source.trend_units }))}</p>` : ""}
      <p>${esc(conclusion + extra)}</p>
      ${check.variable === "precip_gpcp" ? `<p class="hint">${esc(tr("gpcp"))}</p>` : ""}
    </details>`;
  }

  function renderCard(card) {
    const id = card.variable, element = get(`card-${id}`);
    const source = CAT.variables.find((v) => v.id === id);
    const title = esc(tr(`variables.${id}`)), titleId = `resilience-title-${id}`;
    element.setAttribute("aria-labelledby", titleId);
    element.dataset.state = card.status;
    const provenance = `<div class="resilience-source">
      <p><a href="${esc(source.url)}" target="_blank" rel="noopener">${esc(source.product)}</a></p>
      <p class="hint">${esc(source.resolution)}</p></div>`;
    const heading = `<h3 id="${titleId}">${title}</h3>${provenance}`;
    if (!card.result) {
      element.innerHTML = heading + `<p class="resilience-verdict">${esc(tr(card.status))}</p>`;
      return;
    }
    const { result, verdict, advisory } = card;
    const formatted = I18N.response("analysis", card);
    const conclusion = advisory && verdict.code === "trend_detected" ? t("detective.significantInMerra") : formatted.verdict.title;
    const robustness = verdict.robustness;
    const link = detectiveLink(card);
    element.innerHTML = `${heading}
      <div class="resilience-trend">
        <p class="big">${esc(slope(result.slope))} <small>${esc(formatted.trend_units)}</small></p>
        <p class="resilience-verdict ${esc(verdict.code)}">${esc(conclusion)}</p>
      </div>
      <dl class="resilience-metrics">
        ${metric(tr("confidence"), interval(result.ci_low, result.ci_high))}
        ${metric(t("detective.pValue"), fmtP(result.p))}
        ${metric(tr("validMonths"), result.valid_fraction == null ? n(null) :
          tr("percent", { value: I18N.number(100 * result.valid_fraction, { maximumFractionDigits: 1 }) }))}
      </dl>
      <dl class="resilience-metrics resilience-robustness">
        ${metric(tr("direction"), robustness ? `${robustness.same_sign} / ${robustness.windows}` : n(null))}
        ${metric(tr("longSignificant"), robustness ? `${robustness.long_significant} / ${robustness.long_windows}` : n(null))}
      </dl>
      ${advisory ? `<p class="resilience-advisory"><a href="${esc(advisory.source_url)}" target="_blank" rel="noopener">${esc(tr("precipAdvisory"))}</a></p>` : ""}
      ${renderCheck(card)}
      <details class="resilience-source-details">
        <summary>${esc(tr("sourceDetails"))}</summary>
        <p>${esc(source.provider)} · ${esc(source.kind)}</p>
        <p>${esc(source.citation)} <a href="${esc(source.url)}" target="_blank" rel="noopener">${esc(t("common.link"))}</a></p>
        <p>${esc(t("common.licence", { license: source.license }))}</p>
        <ul>${source.caveats.map((line) => `<li>${esc(line)}</li>`).join("")}</ul>
      </details>
      ${link.html}`;
    get(`open-${id}`).onclick = (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      openInDetective(link.params);
    };
  }

  function render() {
    $("#resilience").dataset.state = phase;
    get("status").textContent = statusText();
    get("retry").hidden = phase !== "error" || errorText === "areaError";
    get("retry").textContent = tr(errorText === "periodError" ? "resetPeriod" : "retry");
    get("report").hidden = !report;
    if (!report) return;
    get("area-name").textContent = place.bbox ? t("common.selectedArea") : placeName(place);
    const season = seasons[months] ? t(seasons[months]) : months.split(",").map((m) => monthLabel(+m)).join(", ");
    get("parameters").textContent = report.years ? `${start}–${end} · ${season}` : season;
    get("bounds").textContent = tr("bounds", { coordinates: coordinates(report.bbox) });
    const url = new URL(shareHash(), location.href).href;
    get("print-link").href = url;
    get("print-link").textContent = url;
    report.cards.forEach(renderCard);
    ["csv", "json"].forEach(prepareExport);
    get("methods").innerHTML = Object.keys(report.methods).map((key) =>
      `<li><b>${esc(t(`methods.notes.${key}.label`))}</b> · ${esc(CAT.methods[key])}</li>`).join("");
  }

  async function load() {
    if (request) request.abort();
    const controller = new AbortController();
    request = controller;
    phase = "loading";
    report = null;
    get("link").hidden = true;
    get("share-status").textContent = "";
    render();
    try {
      const data = await fetchReport(params(), { signal: controller.signal });
      if (request !== controller) return;
      report = data;
      start = data.start;
      end = data.end;
      years = data.years;
      phase = data.years ? "ready" : "empty";
      if ($("#resilience").classList.contains("active")) history.replaceState(null, "", shareHash());
      populateYears();
      render();
      $("#resilience").dispatchEvent(new CustomEvent("resilience:ready", { bubbles: true, detail: { report: data } }));
    } catch (error) {
      if (request !== controller) return;
      errorText = {
        "choose at least 5 years within the common period": "periodError",
        "unknown region": "areaError",
        "invalid bbox": "areaError",
        "bbox must be within the world": "areaError",
        "bbox must have west<east and south<north": "areaError",
        "bbox must be west,south,east,north": "areaError",
      }[error.detail] || "loadError";
      phase = "error";
      report = null;
      years = null;
      populateYears();
      render();
    }
  }

  function enter() {
    populatePlaces();
    populateMonths();
    return load();
  }

  function openFrom(area, periodMonths) {
    place = area;
    if (area.bbox) selection = area;
    months = seasonValue(periodMonths);
    start = end = null;
    years = null;
    populateYears();
    $("#tab-resilience").click();
    $("#tab-resilience").focus();
  }

  function localise() {
    populatePlaces();
    populateMonths();
    get("limit-list").innerHTML = limits.map((key) => `<li>${esc(tr(`limits.${key}`))}</li>`).join("");
    render();
  }

  function readLocation(hash) {
    const bbox = hash.get("bbox"), region = hash.get("region");
    place = bbox || region ? { region, bbox: bbox ? bbox.split(",").map(Number) : null } : { region: "central_europe" };
    if (place.bbox) selection = place;
    start = Number(hash.get("start")) || null;
    end = Number(hash.get("end")) || null;
    months = seasonValue(hash.get("months"));
    years = null;
    populateYears();
  }

  function restore(hash) {
    readLocation(hash);
    if ($("#resilience").classList.contains("active")) return enter();
    $("#tab-resilience").click();
  }

  function init() {
    const hash = new URLSearchParams(location.hash.slice(1));
    if (hash.get("view") === "resilience") readLocation(hash);
    get("area").onchange = (event) => {
      place = places[event.target.value];
      start = end = null;
      years = null;
      populateYears();
      load();
    };
    get("months").onchange = (event) => { months = event.target.value; load(); };
    get("start").onchange = (event) => {
      start = +event.target.value;
      end = Math.max(end, start + MIN_PERIOD_SPAN);
      populateYears();
      load();
    };
    get("end").onchange = (event) => {
      end = +event.target.value;
      start = Math.min(start, end - MIN_PERIOD_SPAN);
      populateYears();
      load();
    };
    get("retry").onclick = () => {
      if (errorText === "periodError") start = end = null;
      load();
    };
    get("copy").onclick = async () => {
      const url = new URL(shareHash(), location.href).href;
      try {
        await navigator.clipboard.writeText(url);
        get("share-status").textContent = t("common.copied");
      } catch (error) {
        const field = get("link");
        field.value = url;
        field.hidden = false;
        field.focus();
        field.select();
      }
    };
    get("print").onclick = () => window.print();
    $("#gResilience").onclick = () => {
      if (G.sel) openFrom({ region: G.lastAnalysis && G.lastAnalysis.region, bbox: [...G.sel] });
    };
    $("#detectiveResilience").onclick = () => openFrom({ region: state.region, bbox: state.bbox }, state.months);
    window.addEventListener("beforeprint", () => {
      if (!$("#resilience").classList.contains("active")) return;
      closedOnPrint = $$("#resilience details:not([open])");
      closedOnPrint.forEach((node) => { node.open = true; });
    });
    window.addEventListener("afterprint", () => {
      closedOnPrint.forEach((node) => { node.open = false; });
      closedOnPrint = [];
    });
    localise();
  }

  return { enter, init, localise, restore };
})();
