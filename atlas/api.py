"""HTTP API + static frontend for Earth Evidence Atlas.

Run: uvicorn atlas.api:app --host 0.0.0.0 --port 8000

AI disclosure: generated with Claude (Anthropic) as a coding assistant; team review pending.
"""
from __future__ import annotations

import io
import json
import math
import threading
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import numpy as np
import pandas as pd
import xarray as xr
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import answers
from . import stats as S
from .config import (REGIONS, ROOT, VARIABLES, add_custom_region, cube_path, custom_regions, get_region,
                     prune_custom_regions, touch_custom_region)
from .sources.common import IO_LOCK

# Public mode for the internet-facing demo (ATLAS_PUBLIC=1): no API docs pages, limits on compute jobs.
PUBLIC = os.environ.get("ATLAS_PUBLIC") == "1"
PUBLIC_LIMITS = dict(max_active_jobs=3, per_visitor_active=1, per_visitor_per_hour=8, max_sim_runs=1000)

app = FastAPI(title="Earth Evidence Atlas API", version="0.1.0",
              docs_url=None if PUBLIC else "/docs", redoc_url=None if PUBLIC else "/redoc",
              openapi_url=None if PUBLIC else "/openapi.json")

# Optional clean-up of user-made areas for a public demo, e.g. ATLAS_PRUNE_DAYS=7 ATLAS_MAX_CUSTOM=60.
# Off by default so a local copy never deletes anything.
_PRUNE = (float(os.environ["ATLAS_PRUNE_DAYS"]) if os.environ.get("ATLAS_PRUNE_DAYS") else None,
          int(os.environ.get("ATLAS_MAX_CUSTOM", "1000000")))


def _maybe_prune():
    if _PRUNE[0] is not None or os.environ.get("ATLAS_MAX_CUSTOM"):
        with IO_LOCK:
            prune_custom_regions(_PRUNE[0] if _PRUNE[0] is not None else 1e9, _PRUNE[1])


_maybe_prune()
app.add_middleware(GZipMiddleware, minimum_size=2000)

METHOD_NOTE = {
    "deseasonalisation": "Each calendar month's mean over the selected period is subtracted (anomalies).",
    "trend": "Ordinary least squares slope of the anomalies, reported per decade.",
    "uncertainty": "95% confidence interval with AR(1) effective sample size correction (Santer et al. 2000).",
    "cross_check": "Seasonal Mann–Kendall test and seasonal Sen slope (Hirsch et al. 1982).",
    "map_multiple_testing": "Benjamini–Hochberg false discovery rate across map cells, q = 0.05 (Wilks 2016).",
    "regional_mean": "cos(latitude)-weighted mean of cell anomalies; months with < 50% area coverage are dropped.",
    "minimum_data": f"A trend is computed only if at least {int(S.MIN_FRACTION*100)}% of the selected months are valid.",
}


# ------------------------------------------------------------------ data access
def load(var: str, region: str) -> xr.Dataset:
    with IO_LOCK:  # netCDF4/HDF5 is not thread-safe; endpoints run in a thread pool
        return _load(var, region)


@lru_cache(maxsize=64)
def _load(var: str, region: str) -> xr.Dataset:
    p = cube_path(var, region)
    if var not in VARIABLES or get_region(region) is None:
        raise HTTPException(404, "unknown variable or region")
    if not p.exists():
        raise HTTPException(404, f"data for {var}/{region} has not been built yet")
    return xr.load_dataset(p)


def _months(months: str | None) -> list[int]:
    if not months:
        return list(range(1, 13))
    try:
        ms = sorted({int(m) for m in months.split(",") if m})
    except ValueError:
        raise HTTPException(400, "months must be comma-separated integers 1-12")
    if not ms or any(m < 1 or m > 12 for m in ms):
        raise HTTPException(400, "months must be 1-12")
    return ms


def subset(var, region, start, end, months, bbox=None):
    ds = load(var, region)
    v = VARIABLES[var]
    start = start or v.years[0]
    end = end or v.years[1]
    if end - start + 1 < 5:
        raise HTTPException(400, "choose a period of at least 5 years")
    da = ds["value"].sel(time=slice(f"{start}-01-01", f"{end}-12-31"))
    if bbox:
        w, s, e, n = bbox
        da = da.sel(lat=slice(s, n), lon=slice(w, e))
        if da.sizes["lat"] == 0 or da.sizes["lon"] == 0:  # tiny box: nearest cell
            c = ds["value"].sel(lat=(s + n) / 2, lon=(w + e) / 2, method="nearest")
            da = ds["value"].sel(time=slice(f"{start}-01-01", f"{end}-12-31"),
                                 lat=[float(c.lat)], lon=[float(c.lon)])
    mo = S.month_of(da.time.values) + 1
    da = da.isel(time=np.isin(mo, months))
    return da, start, end


def _bbox(s: str | None):
    if not s:
        return None
    try:
        w, so, e, n = (float(x) for x in s.split(","))
    except ValueError:
        raise HTTPException(400, "bbox must be west,south,east,north")
    if not (w < e and so < n):
        raise HTTPException(400, "bbox must have west<east and south<north")
    return (w, so, e, n)


def _clean(x):
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, np.ndarray):
        return _clean(x.tolist())
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else round(float(x), 6)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def provenance(var, region):
    v = VARIABLES[var]
    ds = load(var, region)
    return dict(product=v.product, provider=v.provider, kind=v.kind, resolution=v.resolution,
                citation=v.citation, url=v.url, license=v.license, caveats=list(v.caveats),
                cube_created=ds.attrs.get("created"),
                processing={k: ds.attrs[k] for k in ds.attrs if k not in ("citation", "provider", "product")})


# ------------------------------------------------------------------ endpoints
@app.get("/api/catalog")
def catalog():
    allreg = {**REGIONS, **custom_regions()}
    avail = {f"{v}/{r}": cube_path(v, r).exists() for v in VARIABLES for r in allreg
             if r in VARIABLES[v].regions or r.startswith("c_")}
    return dict(
        variables=[v.public() for v in VARIABLES.values()],
        regions=[dict(id=r.id, name=r.name, bbox=r.bbox, story=r.story, custom=r.id.startswith("c_"))
                 for r in allreg.values()],
        compute_limits=COMPUTE_LIMITS,
        available=avail, methods=METHOD_NOTE,
        ai_disclosure="Code of this prototype was generated with the help of Claude (Anthropic), an AI assistant. Data values come only from the cited NASA sources.",
    )


@lru_cache(maxsize=256)
def _analysis(var, region, start, end, months_t, bbox_t, min_len):
    months = list(months_t)
    da, start, end = subset(var, region, start, end, months, bbox_t)
    A = S.deseasonalise(da.values.reshape(da.sizes["time"], -1), S.month_of(da.time.values))
    A = A.reshape(da.shape)
    y, cover = S.area_mean(A, da.lat.values)
    # absolute regional mean (for the seasonal-cycle panel): climatology + anomaly
    absmean, _ = S.area_mean(da.values, da.lat.values, min_cover=0.5)
    times = da.time.values
    res = S.analyse_series(times, y)
    mlen = min(min_len, max(5, end - start + 1 - 5))
    mx = S.window_matrix(times, y, min_len=mlen) if end - start + 1 >= 10 else None
    ver = S.verdict(res, mx)
    t = res["t"]
    tm = np.nanmean(t[np.isfinite(res["anomaly"])])
    fit = res["intercept"] + res["slope"] / 10 * t
    # 12-month running mean only makes sense for all-month analyses
    run = pd.Series(res["anomaly"]).rolling(12, center=True, min_periods=9).mean().values \
        if len(months) == 12 else None
    clim = [float(np.nanmean(absmean[S.month_of(times) == m - 1])) if (S.month_of(times) == m - 1).any() else None
            for m in range(1, 13)]
    out = dict(
        variable=var, region=region, start=start, end=end, months=months,
        bbox=bbox_t or get_region(region).bbox,
        cells=int(da.sizes["lat"] * da.sizes["lon"]),
        series=dict(dates=[str(d)[:7] for d in times], anomaly=res["anomaly"], fit=fit,
                    running12=run, coverage=cover, absolute=absmean, t=t, t_mean=tm),
        seasonal_cycle=clim,
        result={k: res[k] for k in ("slope", "ci_low", "ci_high", "p", "n", "n_eff", "r1",
                                      "mk_p", "mk_z", "sen_slope", "valid_fraction")},
        trend_units=VARIABLES[var].trend_units, units=VARIABLES[var].units,
        verdict=ver, matrix=mx, methods=METHOD_NOTE, provenance=provenance(var, region),
    )
    out["answer"] = _answer(out, months_t, bbox_t, min_len)
    return out


def _answer(a, months_t, bbox_t, min_len):
    """Plain-language answer to the variable's question, from the numbers above (see atlas/answers.py)."""
    try:
        var, region = a["variable"], a["region"]
        tmap = _map(var, region, a["start"], a["end"], months_t, 0.05) if bbox_t is None else None
        a = dict(a, bbox_selected=bbox_t is not None)
        compare = cvar = None
        other = answers.PHRASES.get(var, {}).get("compare_with")
        if other and cube_path(other, region).exists():
            o = VARIABLES[other]
            s0, e0 = max(a["start"], o.years[0]), min(a["end"], o.years[1])
            if e0 - s0 >= 7:
                compare = _analysis(other, region, s0, e0, months_t, bbox_t, min_len)
                cvar = o.public()
        return answers.build(VARIABLES[var].public(), get_region(region).name, a, tmap, compare, cvar)
    except Exception as exc:  # an answer must never break the analysis itself
        return dict(question=VARIABLES[a["variable"]].question, headline="", code="error", lines=[],
                    caveat=None, how=[], note=f"Answer unavailable: {exc}")


@app.get("/api/analysis")
def analysis(var: str, region: str, start: int | None = None, end: int | None = None,
             months: str | None = None, bbox: str | None = None, min_len: int = Query(15, ge=5, le=40)):
    out = _analysis(var, region, start, end, tuple(_months(months)), _bbox(bbox), min_len)
    with IO_LOCK:
        touch_custom_region(region)
    return JSONResponse(_clean(out))


@lru_cache(maxsize=128)
def _map(var, region, start, end, months_t, q):
    da, start, end = subset(var, region, start, end, list(months_t))
    T, ny, nx = da.shape
    Y = da.values.reshape(T, -1).astype("float64")
    A = S.deseasonalise(Y, S.month_of(da.time.values))
    valid = np.isfinite(A).mean(0)
    A[:, valid < S.MIN_FRACTION] = np.nan
    o = S.ols_trend(S.decimal_years(da.time.values), A)
    slope = o["slope"] * 10
    p = np.where(valid >= S.MIN_FRACTION, o["p"], np.nan)
    sig, thr = S.bh_fdr(p, q)
    raw_sig = p < 0.05
    fin = np.isfinite(slope)
    lim = float(np.nanpercentile(np.abs(slope[fin]), 98)) if fin.any() else 1.0
    lat, lon = da.lat.values, da.lon.values
    dlat = float(np.median(np.diff(lat))) if ny > 1 else 2.0
    dlon = float(np.median(np.diff(lon))) if nx > 1 else 2.0
    return dict(
        variable=var, region=region, start=start, end=end, months=list(months_t),
        lat=lat, lon=lon, shape=[ny, nx],
        bounds=[[float(lat.min() - dlat / 2), float(lon.min() - dlon / 2)],
                [float(lat.max() + dlat / 2), float(lon.max() + dlon / 2)]],
        slope=slope.reshape(ny, nx), p=p.reshape(ny, nx), sig_fdr=sig.reshape(ny, nx),
        valid_fraction=valid.reshape(ny, nx), color_limit=lim, fdr_q=q, fdr_p_threshold=thr,
        summary=dict(cells_with_trend=int(fin.sum()), cells_total=int(ny * nx),
                     significant_fdr=int(sig.sum()), significant_uncorrected=int(np.nansum(raw_sig)),
                     positive=int((slope[fin] > 0).sum()), negative=int((slope[fin] < 0).sum()),
                     median_slope=float(np.nanmedian(slope)) if fin.any() else None),
        trend_units=VARIABLES[var].trend_units,
    )


@app.get("/api/map")
def trend_map(var: str, region: str, start: int | None = None, end: int | None = None,
              months: str | None = None, q: float = Query(0.05, gt=0, lt=0.5)):
    return JSONResponse(_clean(_map(var, region, start, end, tuple(_months(months)), q)))


@app.get("/api/export.csv")
def export_csv(var: str, region: str, start: int | None = None, end: int | None = None,
               months: str | None = None, bbox: str | None = None):
    out = _analysis(var, region, start, end, tuple(_months(months)), _bbox(bbox), 15)
    s = out["series"]
    df = pd.DataFrame({"month": s["dates"], "regional_mean": s["absolute"], "anomaly": s["anomaly"],
                       "trend_line": s["fit"], "area_coverage": s["coverage"]})
    buf = io.StringIO()
    v = VARIABLES[var]
    buf.write(f"# Earth Evidence Atlas export | variable={v.name} [{v.units}] | region={region} "
              f"bbox={out['bbox']} | period={out['start']}-{out['end']} months={out['months']}\n")
    buf.write(f"# source: {v.citation}\n# trend: {out['result']['slope']:.4g} {v.trend_units} "
              f"(95% CI {out['result']['ci_low']:.4g}..{out['result']['ci_high']:.4g}, p={out['result']['p']:.3g})\n")
    buf.write("# generated by code written with an AI assistant (Claude, Anthropic)\n")
    df.to_csv(buf, index=False, float_format="%.5g")
    fn = f"atlas_{var}_{region}_{out['start']}-{out['end']}.csv"
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{fn}"'})


@app.get("/api/export.json")
def export_json(var: str, region: str, start: int | None = None, end: int | None = None,
                months: str | None = None, bbox: str | None = None):
    out = _clean(_analysis(var, region, start, end, tuple(_months(months)), _bbox(bbox), 15))
    out.pop("series", None)
    fn = f"atlas_{var}_{region}_{out['start']}-{out['end']}_evidence.json"
    return Response(json.dumps(out, indent=2, ensure_ascii=False), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{fn}"'})


@app.get("/api/simulate")
def simulate(seed: int = 7, years: int = Query(12, ge=5, le=60), phi: float = Query(0.6, ge=0, le=0.95),
             sigma: float = Query(0.5, gt=0, le=5)):
    """SIMULATION – not satellite observations. Trendless AR(1) noise, to show false alarms."""
    rng = np.random.default_rng(seed)
    n = years * 12
    x = np.zeros(n)
    e = rng.normal(0, sigma, n)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    times = pd.date_range("2001-01-01", periods=n, freq="MS").values
    t = S.decimal_years(times)
    o = S.ols_trend(t, x)
    from scipy import stats as st
    naive_p = float(2 * st.t.sf(abs(o["slope"][0] / o["se"][0]), n - 2))
    return _clean(dict(label="SIMULATION – not satellite observations", seed=seed, years=years, phi=phi,
                       sigma=sigma, true_trend=0.0, dates=[str(d)[:7] for d in times], values=x,
                       slope=o["slope"][0] * 10, naive_p=naive_p, corrected_p=o["p"][0],
                       n_eff=o["n_eff"][0], fit=o["intercept"][0] + o["slope"][0] * t))


@app.get("/api/simulate_many")
def simulate_many(runs: int = Query(200, ge=10, le=5000), years: int = Query(12, ge=5, le=60),
                  phi: float = Query(0.6, ge=0, le=0.95), seed: int = 1000):
    """SIMULATION – how often trendless AR(1) series are called significant (naive vs corrected)."""
    if PUBLIC and runs > PUBLIC_LIMITS["max_sim_runs"]:
        raise HTTPException(400, f"at most {PUBLIC_LIMITS['max_sim_runs']} runs on the public demo")
    from scipy import stats as st
    rng = np.random.default_rng(seed)
    n = years * 12
    e = rng.normal(0, 1, (n, runs))
    x = np.zeros((n, runs))
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    t = S.decimal_years(pd.date_range("2001-01-01", periods=n, freq="MS").values)
    o = S.ols_trend(t, x)
    naive_p = 2 * st.t.sf(np.abs(o["slope"] / o["se"]), n - 2)
    return dict(label="SIMULATION – not satellite observations", runs=runs, years=years, phi=phi,
                naive_significant=int((naive_p < 0.05).sum()), corrected_significant=int((o["p"] < 0.05).sum()))

# ------------------------------------------------------------------ globe support
COMPUTE_LIMITS = {
    "modis_pc": dict(max_side_deg=8.0, max_area_deg2=40.0, seconds_per_deg2=7.0),
    "power": dict(max_side_deg=30.0, max_area_deg2=600.0, seconds_per_deg2=0.05),
    "gistemp": dict(max_side_deg=360.0, max_area_deg2=64800.0, seconds_per_deg2=0.0),
}


def _contains(outer, inner):
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


@app.get("/api/layers")
def layers(var: str):
    if var not in VARIABLES:
        raise HTTPException(404, "unknown variable")
    out = []
    for r in {**REGIONS, **custom_regions()}.values():
        if cube_path(var, r.id).exists():
            out.append(dict(region=r.id, name=r.name, bbox=r.bbox, custom=r.id.startswith("c_")))
    return out


@lru_cache(maxsize=64)
def _yearly(var, region, months_t):
    ds = load(var, region)
    da = ds["value"]
    mo = S.month_of(da.time.values) + 1
    da = da.isel(time=np.isin(mo, list(months_t)))
    T, ny, nx = da.shape
    A = S.deseasonalise(da.values.reshape(T, -1).astype("float64"), S.month_of(da.time.values))
    yrs = np.asarray(da.time.values, dtype="datetime64[Y]").astype(int) + 1970
    years = sorted(set(yrs.tolist()))
    frames = np.full((len(years), ny * nx), np.nan)
    for k, y in enumerate(years):
        sel = A[yrs == y]
        ok = np.isfinite(sel).sum(0) >= max(1, math.ceil(sel.shape[0] * 2 / 3))
        with S._quiet():
            frames[k, ok] = np.nanmean(sel[:, ok], 0)
    fin = np.isfinite(frames)
    lim = float(np.nanpercentile(np.abs(frames[fin]), 98)) if fin.any() else 1.0
    return years, frames.reshape(len(years), ny, nx), lim, da.lat.values, da.lon.values


@app.get("/api/frame")
def frame(var: str, region: str, year: int, months: str | None = None):
    """Mean anomaly of one year (vs the cube's full period, same calendar months) for every cell."""
    years, frames, lim, lat, lon = _yearly(var, region, tuple(_months(months)))
    if year not in years:
        raise HTTPException(404, f"year must be within {years[0]}-{years[-1]}")
    return JSONResponse(_clean(dict(
        variable=var, region=region, year=year, years=[years[0], years[-1]], lat=lat, lon=lon,
        values=frames[years.index(year)], color_limit=lim, units=VARIABLES[var].units,
        baseline=f"{years[0]}-{years[-1]} mean of the same calendar months")))


JOBS: dict[str, dict] = {}
_EXEC = ThreadPoolExecutor(max_workers=2)


def _run_job(jid):
    from .sources import gistemp, modis_pc, power
    job = JOBS[jid]
    fetch = {"power": power.fetch, "gistemp": gistemp.fetch, "modis_pc": modis_pc.fetch}[VARIABLES[job["var"]].source]
    job["status"] = "running"

    def prog(frac, msg):
        job["progress"] = round(float(frac), 3)
        job["message"] = msg

    try:
        fetch(job["var"], job["region"], log=lambda m: job.__setitem__("message", m.strip()), progress=prog)
        job.update(status="done", progress=1.0, message="ready", finished=time.time())
    except Exception as e:  # report to the UI, keep the server alive
        job.update(status="error", message=f"{type(e).__name__}: {e}"[:300], finished=time.time())


def _visitor(request: Request) -> str:
    """Visitor address; behind Tailscale Funnel / a proxy the real one is in X-Forwarded-For."""
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "?")


def _check_public_quota(who: str) -> None:
    now = time.time()
    active = [j for j in JOBS.values() if j["status"] in ("queued", "running")]
    if len(active) >= PUBLIC_LIMITS["max_active_jobs"]:
        raise HTTPException(429, "The demo server is busy computing other areas. Please try again in a minute.")
    if sum(j.get("who") == who for j in active) >= PUBLIC_LIMITS["per_visitor_active"]:
        raise HTTPException(429, "Your previous area is still being computed. Please wait for it to finish.")
    if sum(j.get("who") == who and now - j["started"] < 3600 for j in JOBS.values()) >= PUBLIC_LIMITS["per_visitor_per_hour"]:
        raise HTTPException(429, "Hourly limit of new areas on the public demo reached. Built areas still work.")


@app.post("/api/compute")
def compute(request: Request, var: str = Body(...), bbox: list[float] = Body(...)):
    """Make data for (var, bbox) available: reuse a built cube that covers it, or start a job."""
    if var not in VARIABLES:
        raise HTTPException(404, "unknown variable")
    if len(bbox) != 4:
        raise HTTPException(400, "bbox must be [west, south, east, north]")
    w, s, e, n = (float(x) for x in bbox)
    w, e = max(w, -180.0), min(e, 180.0)
    s, n = max(s, -89.0), min(n, 89.0)
    if not (w < e and s < n):
        raise HTTPException(400, "empty bbox (areas crossing the date line are not supported yet)")
    v = VARIABLES[var]
    box = (w, s, e, n)
    for r in {**REGIONS, **custom_regions()}.values():
        if cube_path(var, r.id).exists() and _contains(r.bbox, box):
            return dict(status="ready", region=r.id, bbox=box, message=f"covered by existing data: {r.name}")
    lim = COMPUTE_LIMITS[v.source]
    side, area = max(e - w, n - s), (e - w) * (n - s)
    if side > lim["max_side_deg"] or area > lim["max_area_deg2"]:
        raise HTTPException(400, f"area too large for {v.product}: max {lim['max_side_deg']}° per side and "
                                 f"{lim['max_area_deg2']} deg² (selected {e - w:.1f}° × {n - s:.1f}°)")
    if v.source == "power" and side < 1.0:  # POWER regional needs a box of a few grid cells
        cx, cy = (w + e) / 2, (s + n) / 2
        w, e, s, n = cx - 1, cx + 1, max(cy - 1, -89), min(cy + 1, 89)
        box = (w, s, e, n)
    _maybe_prune()
    reg = add_custom_region(box)
    if cube_path(var, reg.id).exists():
        return dict(status="ready", region=reg.id, bbox=box, message="already computed")
    for jid, j in JOBS.items():
        if j["var"] == var and j["region"] == reg.id and j["status"] in ("queued", "running"):
            return dict(status="queued", job=jid, region=reg.id, bbox=box)
    who = _visitor(request)
    if PUBLIC:
        _check_public_quota(who)
    jid = uuid.uuid4().hex[:12]
    JOBS[jid] = dict(id=jid, var=var, region=reg.id, bbox=box, status="queued", progress=0.0,
                     message="waiting", started=time.time(), who=who,
                     estimate_s=round(5 + area * lim["seconds_per_deg2"] * (v.years[1] - v.years[0] + 1) / 24))
    _EXEC.submit(_run_job, jid)
    return dict(status="queued", job=jid, region=reg.id, bbox=box, estimate_s=JOBS[jid]["estimate_s"])


@app.get("/api/jobs/{jid}")
def job_status(jid: str):
    if jid not in JOBS:
        raise HTTPException(404, "unknown job")
    j = dict(JOBS[jid])
    j.pop("who", None)  # never show visitor addresses
    j["elapsed_s"] = round(time.time() - j["started"], 1)
    return j


@app.get("/api/health")
def health():
    return {"ok": True}


WEB = ROOT / "web"
app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")
