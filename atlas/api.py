"""HTTP API + static frontend for Earth Evidence Atlas.

Run: uvicorn atlas.api:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import io
import json
import logging
import math
import threading
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Literal

import numpy as np
import pandas as pd
import xarray as xr
from scipy import stats as st
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import answers
from . import stats as S
from .config import (CROSS_CHECKS, REGIONS, ROOT, VARIABLES, add_custom_region, cube_path, custom_regions, get_region,
                     prune_custom_regions, touch_custom_region)
from .sources.common import IO_LOCK

logger = logging.getLogger(__name__)

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
    "uncertainty": ("Two memory corrections: month to month (AR(1) for the actual sampling, bias-corrected; "
                    "Santer et al. 2000) and year to year (the same test on yearly means). The p-value is the "
                    "larger of the two and the 95% interval covers both, so a trend counts only if both agree."),
    "cross_check": ("Seasonal Mann–Kendall with the Hirsch & Slack (1984) correction for dependent months, and "
                    "Mann–Kendall on yearly means with the Hamed & Rao (1998) correction; the larger p is shown. "
                    "Seasonal Sen slope."),
    "calibration": ("Checked on synthetic series without a trend: with month-to-month memory up to 0.9, seasons "
                    "and gaps, at most about 6% are called significant (the target is 5%). Slow decade-long swings "
                    "remain hard: 5–12% instead of 12–39% before this correction."),
    "map_multiple_testing": "Benjamini–Hochberg false discovery rate across map cells, q = 0.05 (Wilks 2016).",
    "period_choice": ("The map correction covers grid cells, not the choice of period, season or variable: the "
                      "more combinations you try, the more likely one looks significant by chance. The squares in "
                      "“Does it hold?” overlap, so they are not independent repeats."),
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
        selection = da.sel(lat=slice(s, n), lon=slice(w, e))
        lat = selection.lat if selection.sizes["lat"] else da.lat.sel(lat=[(s + n) / 2], method="nearest")
        lon = selection.lon if selection.sizes["lon"] else da.lon.sel(lon=[(w + e) / 2], method="nearest")
        da = da.sel(lat=lat, lon=lon)
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
    )


@lru_cache(maxsize=256)
def _analysis(var, region, start, end, months_t, bbox_t, min_len, checks=True):
    """checks=False: no independent-dataset check and no answer (used for the check itself)."""
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
        result={k: res[k] for k in ("slope", "ci_low", "ci_high", "p", "p_month", "p_year", "binding",
                                      "n", "n_eff", "n_year", "n_eff_year", "n_years", "r1", "rho", "rho_year",
                                      "mk_p", "mk_p_seasonal", "mk_p_year", "mk_z", "sen_slope",
                                      "valid_fraction")},
        trend_units=VARIABLES[var].trend_units, units=VARIABLES[var].units,
        verdict=ver, matrix=mx, methods=METHOD_NOTE, provenance=provenance(var, region),
    )
    if checks:
        out["cross_check"] = _cross_check(out, months_t, bbox_t, min_len)
        out["answer"] = _answer(out, months_t, bbox_t, min_len)
    return out


def _agreement(a: dict, b: dict, p_diff: float | None) -> str:
    """Compare two trend results for the same area and years. 'Significant' = p < 0.05 in the app's
    two-scale test. Sizes count as different when the trend of the difference series is itself
    significant (the trend-difference test of Santer et al. 2000, with the same memory corrections)."""
    sa, sb = np.sign(a["slope"]), np.sign(b["slope"])
    siga, sigb = a["p"] < 0.05, b["p"] < 0.05
    if sa == sb and siga and sigb:
        return "same_direction_different_size" if (p_diff is not None and p_diff < 0.05) else "agree"
    if sa == sb:
        return "one_significant" if (siga or sigb) else "neither_significant"
    return "disagree" if (siga or sigb) else "unclear"


def _cross_check(a: dict, months_t, bbox_t, min_len):
    """The same analysis with an independent dataset (config.CROSS_CHECKS) for the same area and the
    common period. Uses the region's cube, or the global cube of a gridded product cut to the area."""
    var, region = a["variable"], a["region"]
    other = CROSS_CHECKS.get(var)
    if not other:
        return None
    o = VARIABLES[other]
    if cube_path(other, region).exists():
        oreg, obox = region, bbox_t
    elif cube_path(other, "world").exists() and region != "world":
        oreg, obox = "world", tuple(bbox_t or get_region(region).bbox)
    else:
        return None
    s0, e0 = max(a["start"], o.years[0]), min(a["end"], o.years[1])
    if e0 - s0 + 1 < 10:
        return None
    try:
        b = _analysis(other, oreg, s0, e0, months_t, obox, min_len, checks=False)
        here = a if (s0, e0) == (a["start"], a["end"]) else _analysis(var, region, s0, e0, months_t, bbox_t,
                                                                      min_len, checks=False)
    except HTTPException:
        return None
    ra, rb = here["result"], b["result"]
    if any(r.get(k) is None or not np.isfinite(r[k]) for r in (ra, rb) for k in ("slope", "p", "ci_low", "ci_high")):
        return None
    # trend of the difference series (same months only): do the two records change by the same amount?
    da_ = pd.Series(np.asarray(here["series"]["anomaly"], float), index=here["series"]["dates"])
    db_ = pd.Series(np.asarray(b["series"]["anomaly"], float), index=b["series"]["dates"])
    both = da_.index.intersection(db_.index)
    diff = (da_[both] - db_[both]).values
    p_diff = slope_diff = None
    if np.isfinite(diff).sum() >= 60:
        rd = S.analyse_series(np.array(both, dtype="datetime64[M]"), diff)
        p_diff, slope_diff = rd["p"], rd["slope"]
    return dict(variable=other, name=o.name, product=o.product, kind=o.kind, start=s0, end=e0,
                slope=rb["slope"], ci_low=rb["ci_low"], ci_high=rb["ci_high"], p=rb["p"], verdict=b["verdict"]["code"],
                main_slope=ra["slope"], main_ci_low=ra["ci_low"], main_ci_high=ra["ci_high"], main_p=ra["p"],
                difference_slope=slope_diff, difference_p=p_diff,
                agreement=_agreement(ra, rb, p_diff), sizes_differ=bool(p_diff is not None and p_diff < 0.05),
                trend_units=o.trend_units,
                cells=b["cells"], bbox=b["bbox"])


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
                compare = _analysis(other, region, s0, e0, months_t, bbox_t, min_len, checks=False)
                cvar = o.public()
        answer = answers.build(VARIABLES[var].public(), get_region(region).name, a, tmap, compare, cvar)
        if var == "precip":
            w, s, e, n = a["bbox"]
            aw, south, ae, north = REGIONS["amazon_arc"].bbox
            if w < ae and aw < e and s < north and south < n:
                answer["source_url"] = "https://doi.org/10.1175/JCLI-D-16-0570.1"
                answer["caveat"] = ("Published assessments document breaks in corrected MERRA-2 rainfall in South America. "
                                    "Check a second dataset for the same area, season and period.")
                if answer["code"] in ("trend_detected", "depends_on_period", "significance_depends_on_period"):
                    trend = a["result"]["slope"]
                    answer["lines"][0] = (f"Estimated MERRA-2 rainfall trend: {answers.num(trend)} "
                                          f"mm/day per decade ({a['start']}–{a['end']}, {answers.season_text(a['months'])}).")
                    cc = a.get("cross_check")
                    less = trend < 0
                    if cc and cc["variable"] == "precip_gpcp":
                        answer["headline"] = {
                            "agree": "Less rainfall in both MERRA-2 and GPCP." if less else "More rainfall in both MERRA-2 and GPCP.",
                            "same_direction_different_size": ("Less rainfall in MERRA-2 and GPCP, by different amounts."
                                                              if less else "More rainfall in MERRA-2 and GPCP, by different amounts."),
                            "one_significant": "MERRA-2 and GPCP point the same way, but only one is significant.",
                            "neither_significant": "MERRA-2 and GPCP point the same way, but neither is significant.",
                            "disagree": "MERRA-2 and GPCP disagree. Treat it with care.",
                            "unclear": "MERRA-2 and GPCP disagree. Treat it with care.",
                        }[cc["agreement"]]
                    elif answer["code"] == "trend_detected":
                        answer["headline"] = ("MERRA-2 suggests less rainfall. Needs confirmation." if less else
                                              "MERRA-2 suggests more rainfall. Needs confirmation.")
        return answer
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
    o = S.trend_test(S.decimal_years(da.time.values), A)   # same two-scale test as the headline result
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


VALIDATION_PAIRS = (("t2m", "gistemp"), ("precip", "precip_gpcp"), ("lst_day", "lst_day_aqua"))


@lru_cache(maxsize=1)
def _validation():
    """Live validation evidence for the built-in regions: each result against an independent dataset for
    the same area and years, and how much of the MODIS record the quality screening kept."""
    rows = []
    for rid in ("central_europe", "nw_india", "amazon_arc"):
        for var, other in VALIDATION_PAIRS:
            if not (cube_path(var, rid).exists() and cube_path(other, rid).exists()):
                continue
            a = _analysis(var, rid, None, None, tuple(range(1, 13)), None, 15)
            cc = a.get("cross_check")
            if not cc or cc["variable"] != other:
                continue
            rows.append(dict(region=rid, variable=var, other=other, start=cc["start"], end=cc["end"],
                             slope=cc["main_slope"], p=cc["main_p"], other_slope=cc["slope"], other_p=cc["p"],
                             difference_p=cc["difference_p"], agreement=cc["agreement"],
                             sizes_differ=cc["sizes_differ"], trend_units=cc["trend_units"]))
    quality = []
    for var in ("ndvi", "lst_day", "lst_day_aqua"):
        for rid in ("central_europe", "nw_india", "amazon_arc"):
            if cube_path(var, rid).exists():
                attrs = load(var, rid).attrs
                quality.append(dict(variable=var, region=rid, kept_share=attrs.get("qa_kept_share"),
                                    rule=attrs.get("quality_mask"), pixels=attrs.get("qa_pixels_with_values")))
    return dict(cross_checks=rows, quality=quality, calibration=CALIBRATION)


# Monte Carlo study of the trend tests (README, "Metody statystyczne i kalibracja"; tests/test_stats.py)
CALIBRATION = dict(
    target=0.05, scenarios="AR(1) memory 0–0.9, 10/24/45 years, all months/Jun–Aug/Dec–Feb, 0 or 20% gaps, "
                           "seasonally changing variance; 1000 trendless series each",
    trend_test=dict(old_max=0.09, new_min=0.016, new_max=0.065),
    rank_test=dict(old_max=0.67, new_min=0.005, new_max=0.066),
    slow_swings=dict(old=[0.12, 0.39], new=[0.05, 0.12]),
)


@app.get("/api/validation")
def validation():
    return JSONResponse(_clean(_validation()))


@app.get("/api/map")
def trend_map(var: str, region: str, start: int | None = None, end: int | None = None,
              months: str | None = None, q: float = Query(0.05, gt=0, lt=0.5)):
    return JSONResponse(_clean(_map(var, region, start, end, tuple(_months(months)), q)))


def _evidence_attachment(content, media_type, filename):
    return Response(content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


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
    df.to_csv(buf, index=False, float_format="%.5g")
    fn = f"atlas_{var}_{region}_{out['start']}-{out['end']}.csv"
    return _evidence_attachment(buf.getvalue(), "text/csv", fn)


@app.get("/api/export.json")
def export_json(var: str, region: str, start: int | None = None, end: int | None = None,
                months: str | None = None, bbox: str | None = None):
    out = _clean(_analysis(var, region, start, end, tuple(_months(months)), _bbox(bbox), 15))
    out.pop("series", None)
    fn = f"atlas_{var}_{region}_{out['start']}-{out['end']}_evidence.json"
    return _evidence_attachment(json.dumps(out, indent=2, ensure_ascii=False), "application/json", fn)


# ------------------------------------------------------------------ resilience brief
RESILIENCE_VARIABLES = ("t2m", "lst_day", "precip", "soil_root")
RESILIENCE_LIMITS = {
    "exposure": "Regional exposure is one input to a facility risk assessment, which also needs local information about the site and its safeguards.",
    "history": "Historical monthly records show past changes. Weather alerts and climate projections require other data and methods.",
    "water": "Rainfall and soil wetness describe drying conditions. Estimating water supply requires local measurements or a hydrological model.",
    "heat": "Air and land surface temperatures measure different things. Monthly means cannot give hot-day counts or human heat stress.",
    "shared": "The POWER variables share the MERRA-2 reanalysis, so agreement between them does not count as independent confirmation.",
    "scale": "The grid resolution sets the spatial scale. A regional trend cannot describe a building's microclimate.",
    "causes": "Statistical significance describes the evidence for a trend. Its causes require a separate analysis.",
    "windows": "The time windows overlap and share observations.",
}


@app.get("/api/resilience")
def resilience(region: str | None = None, bbox: str | None = None, start: int | None = None,
               end: int | None = None, months: str | None = None,
               format: Literal["csv", "json"] | None = None):
    """Assemble a brief from existing cubes and the same analysis as Detective."""
    area = _bbox(bbox)
    regions = {**REGIONS, **custom_regions()}
    if area is None and region is None:
        region = "central_europe"
    selected = regions.get(region)
    if selected is None and region is not None:
        raise HTTPException(404, "unknown region")
    if area is None:
        area = tuple(selected.bbox)
    if not _contains(REGIONS["world"].bbox, area):
        raise HTTPException(400, "bbox must be within the world")
    months_t = tuple(_months(months))
    containing = [r for r in regions.values() if _contains(r.bbox, area)]
    containing.sort(key=lambda r: (r.id != region, (r.bbox[2] - r.bbox[0]) * (r.bbox[3] - r.bbox[1]), r.id))
    cards = []
    for var in RESILIENCE_VARIABLES:
        source = next((r for r in containing if cube_path(var, r.id).exists()), None)
        years = None
        if source:
            time = load(var, source.id).time
            chosen = time.where(time.dt.month.isin(months_t), drop=True)
            if chosen.size:
                first, last = VARIABLES[var].years
                lo, hi = max(int(chosen.dt.year.min()), first), min(int(chosen.dt.year.max()), last)
                if lo <= hi:
                    years = (lo, hi)
        cards.append(dict(variable=var, data_region=source.id if source else None, years=years,
                          status="missing_cube" if source is None else "missing_months" if years is None else "no_common_period",
                          result=None, verdict=None, cross_check=None, provenance=None))

    ranges = [c["years"] for c in cards if c["years"] is not None]
    common = (max(y[0] for y in ranges), min(y[1] for y in ranges)) if ranges else None
    if common and common[1] - common[0] >= 4:
        start = common[0] if start is None else start
        end = common[1] if end is None else end
        if common[0] <= start <= end - 4 and end <= common[1]:
            for card in cards:
                if card["years"] is None:
                    continue
                var, rid = card["variable"], card["data_region"]
                cut = None if area == tuple(regions[rid].bbox) else area
                a = _analysis(var, rid, start, end, months_t, cut, 15)
                card.update({k: a[k] for k in ("result", "verdict", "cross_check", "provenance", "trend_units", "cells")})
                card.update(status="ready", analysis_bbox=cut)
                if a["cross_check"]:
                    card["cross_check_source"] = VARIABLES[a["cross_check"]["variable"]].public()
                if a["answer"].get("source_url"):
                    card["advisory"] = {key: a["answer"][key] for key in ("caveat", "source_url")}
        else:
            raise HTTPException(400, "choose at least 5 years within the common period")
    else:
        common = start = end = None
    out = _clean(dict(region=region, area_name=selected.name if selected else None, bbox=area, start=start, end=end,
                      months=months_t, years=common, cards=cards, methods=METHOD_NOTE, limitations=RESILIENCE_LIMITS))
    # Keep the exact coordinates used in _analysis for reopening and sharing selections.
    out["bbox"] = area
    for card, cleaned in zip(cards, out["cards"]):
        if "analysis_bbox" in card:
            cleaned["analysis_bbox"] = card["analysis_bbox"]
    if format == "csv":
        buf = io.StringIO()
        buf.write("# Earth Evidence Atlas – Environmental Resilience Brief\n")
        for key in ("region", "area_name", "bbox", "start", "end", "months", "years", "methods", "limitations"):
            buf.write(f"# {key}: {json.dumps(out[key], ensure_ascii=False)}\n")
        pd.json_normalize(out["cards"]).to_csv(buf, index=False)
        return _evidence_attachment(buf.getvalue(), "text/csv", "atlas_resilience.csv")
    if format == "json":
        return _evidence_attachment(json.dumps(out, indent=2, ensure_ascii=False), "application/json", "atlas_resilience.json")
    return JSONResponse(out)


@app.get("/api/simulate")
def simulate(seed: int = 7, years: int = Query(12, ge=5, le=60), phi: float = Query(0.6, ge=0, le=0.95),
             sigma: float = Query(0.5, gt=0, le=5), scenario: Literal["noise", "step"] = "noise"):
    """Synthetic AR(1) noise, optionally with one change in its mean halfway through."""
    rng = np.random.default_rng(seed)
    n = years * 12
    x = np.zeros(n)
    e = rng.normal(0, sigma, n)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    halfway = n // 2
    if scenario == "step":
        x[halfway:] += 5 * sigma
    times = pd.date_range("2001-01-01", periods=n, freq="MS").values
    t = S.decimal_years(times)
    o = S.trend_test(t, x)   # the app's own two-scale memory correction
    naive_p = float(2 * st.t.sf(abs(o["slope"][0] / o["se"][0]), n - 2))
    result = dict(label="SIMULATION – not satellite observations", seed=seed, years=years, phi=phi,
                  sigma=sigma, true_trend=0.0, dates=[str(d)[:7] for d in times], values=x,
                  slope=o["slope"][0] * 10, naive_p=naive_p, corrected_p=o["p"][0],
                  n_eff=o["n_eff"][0], fit=o["intercept"][0] + o["slope"][0] * t)
    if scenario == "step":
        result["change_date"] = result["dates"][halfway]
        result["ci_low"], result["ci_high"] = 10 * o["ci_low"][0], 10 * o["ci_high"][0]
        result["segments"] = []
        for section in (slice(0, halfway), slice(halfway, n)):
            seg_t = t[section]
            fit = S.trend_test(seg_t, x[section])
            result["segments"].append(dict(
                dates=result["dates"][section], fit=fit["intercept"][0] + fit["slope"][0] * seg_t,
                slope=10 * fit["slope"][0], p=fit["p"][0],
                ci_low=10 * fit["ci_low"][0], ci_high=10 * fit["ci_high"][0],
            ))
    return _clean(result)


@app.get("/api/simulate_many")
def simulate_many(runs: int = Query(200, ge=10, le=5000), years: int = Query(12, ge=5, le=60),
                  phi: float = Query(0.6, ge=0, le=0.95), seed: int = 1000):
    """SIMULATION – how often trendless AR(1) series are called significant (naive vs corrected)."""
    if PUBLIC and runs > PUBLIC_LIMITS["max_sim_runs"]:
        raise HTTPException(400, f"at most {PUBLIC_LIMITS['max_sim_runs']} runs on the public demo")
    rng = np.random.default_rng(seed)
    n = years * 12
    e = rng.normal(0, 1, (n, runs))
    x = np.zeros((n, runs))
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    t = S.decimal_years(pd.date_range("2001-01-01", periods=n, freq="MS").values)
    o = S.trend_test(t, x)
    naive_p = 2 * st.t.sf(np.abs(o["slope"] / o["se"]), n - 2)
    naive = int((naive_p < 0.05).sum())
    corrected = int((o["p"] < 0.05).sum())
    return dict(label="SIMULATION – not satellite observations", runs=runs, years=years, phi=phi,
                naive_significant=naive, corrected_significant=corrected,
                naive_interval=list(st.binomtest(naive, runs).proportion_ci(method="wilson")),
                corrected_interval=list(st.binomtest(corrected, runs).proportion_ci(method="wilson")))

# ------------------------------------------------------------------ globe support
COMPUTE_LIMITS = {
    "modis_pc": dict(max_side_deg=8.0, max_area_deg2=40.0, seconds_per_deg2=2.5),  # native pixels + quality layer
    "power": dict(max_side_deg=30.0, max_area_deg2=600.0, seconds_per_deg2=0.05, pads_small_areas=True),
    "gistemp": dict(max_side_deg=360.0, max_area_deg2=64800.0, seconds_per_deg2=0.0),
    "gpcp": dict(max_side_deg=360.0, max_area_deg2=64800.0, seconds_per_deg2=0.0),
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
    from .sources import gistemp, gpcp, modis_pc, power
    job = JOBS[jid]
    fetch = {"power": power.fetch, "gistemp": gistemp.fetch, "modis_pc": modis_pc.fetch,
             "gpcp": gpcp.fetch}[VARIABLES[job["var"]].source]
    job["status"] = "running"

    def prog(frac, msg):
        job["progress"] = round(float(frac), 3)
        job["message"] = msg

    try:
        fetch(job["var"], job["region"], log=lambda m: job.__setitem__("message", m.strip()), progress=prog)
        job.update(status="done", progress=1.0, message="ready", finished=time.time())
    except Exception:
        logger.exception("Data download failed for %s/%s", job["var"], job["region"])
        job.update(status="error", message="Could not download data for this area. Try again or select another area.",
                   finished=time.time())


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
    _maybe_prune()
    # Register a box containing the selection even when its edges fall between two hundredths of a degree.
    region_box = (math.floor(w * 100) / 100, math.floor(s * 100) / 100,
                  math.ceil(e * 100) / 100, math.ceil(n * 100) / 100) if v.source == "power" else box
    reg = add_custom_region(region_box)
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
