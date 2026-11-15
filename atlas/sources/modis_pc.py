"""MODIS Terra/Aqua (MOD13A1 NDVI, MOD11A2/MYD11A2 LST) via Microsoft Planetary Computer COGs.

No NASA Earthdata Login needed: the Planetary Computer mirrors the NASA LP DAAC
v061 products as cloud-optimised GeoTIFFs. Every composite is read at its native
resolution (500 m NDVI, 1 km LST) together with its per-pixel quality layer, only
for the window that covers the region. Pixels the quality layer rejects are removed
before anything is averaged (the COG overviews cannot be used for this: their
quality bands are averaged bit fields, which are meaningless). Sinusoidal pixel
centres are converted to lat/lon and averaged into a regular 0.1° grid; a cell
enters a composite only if at least MIN_GOOD_FRACTION of its pixels pass the
quality test, then composites are averaged into calendar months.

Quality rules (product user guides):
* MOD13A1 pixel reliability (Didan et al., MOD13 C6.1 User Guide, Table 4):
  keep 0 (good) and 1 (marginal); drop 2 (snow/ice), 3 (cloudy) and fill.
* MOD11A2/MYD11A2 QC_Day (Wan, MOD11 C6.1 User Guide, Table 18): keep mandatory
  QA 00 (good), or 01 (other quality) only when the average LST error is <= 2 K
  (bits 6–7 <= 01); drop pixels not produced (cloud or other reasons).
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
from rasterio.windows import Window

from ..config import RAW_DIR, VARIABLES, get_region
from .common import month_index, write_cube

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "6")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.TIF")

import planetary_computer as pc  # noqa: E402
import pystac_client  # noqa: E402
import rasterio  # noqa: E402

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
R_SPHERE = 6371007.181  # MODIS sinusoidal sphere radius (m)
GRID = 0.1

MIN_GOOD_FRACTION = 0.2   # share of a 0.1° cell's pixels that must pass QA in one composite


def _ndvi_ok(q):
    return q <= 1                                     # 0 good, 1 marginal (255 = fill)


def _lst_ok(q):
    q = q.astype(np.uint8)
    mandatory, lst_err = q & 3, q >> 6
    return (mandatory == 0) | ((mandatory == 1) & (lst_err <= 1))


QA_RULE = {
    "ndvi": "MOD13A1 pixel reliability 0 (good) or 1 (marginal) kept; snow/ice, cloudy and fill removed",
    "lst": "QC_Day mandatory QA 00, or 01 with average LST error <= 2 K, kept; cloud/not produced removed",
}

SPEC = {
    "ndvi": dict(collection="modis-13A1-061", prefix="MOD13A1", asset="500m_16_days_NDVI",
                 qa_asset="500m_16_days_pixel_reliability", qa_ok=_ndvi_ok, qa_rule=QA_RULE["ndvi"],
                 vmin=-2000, vmax=10000, scale=1e-4, offset=0.0),
    "lst_day_aqua": dict(collection="modis-11A2-061", prefix="MYD11A2", asset="LST_Day_1km",
                         qa_asset="QC_Day", qa_ok=_lst_ok, qa_rule=QA_RULE["lst"],
                         vmin=7500, vmax=65535, scale=0.02, offset=-273.15),
    "lst_day": dict(collection="modis-11A2-061", prefix="MOD11A2", asset="LST_Day_1km",
                    qa_asset="QC_Day", qa_ok=_lst_ok, qa_rule=QA_RULE["lst"],
                    vmin=7500, vmax=65535, scale=0.02, offset=-273.15),
}

_geom_cache: dict = {}


def _grid(bbox):
    w, s, e, n = bbox
    lat = np.round(np.arange(s + GRID / 2, n, GRID), 4)
    lon = np.round(np.arange(w + GRID / 2, e, GRID), 4)
    return lat, lon


def _bins(transform, shape, bbox, lat, lon):
    """Window (row0, col0, h, w) of a native-resolution tile that covers the box, the flat 0.1° bin
    index of every pixel in it (-1 = outside), and the number of pixels per cell."""
    key = (tuple(transform), shape, bbox)
    if key in _geom_cache:
        return _geom_cache[key]
    rows, cols = np.mgrid[0:shape[0], 0:shape[1]].astype("int32")
    x = transform.c + (cols + 0.5) * transform.a
    y = transform.f + (rows + 0.5) * transform.e
    la = np.degrees(y / R_SPHERE)
    with np.errstate(divide="ignore", invalid="ignore"):
        lo = np.degrees(x / (R_SPHERE * np.cos(np.radians(la))))
    w, s, e, n = bbox
    i = np.floor((la - s) / GRID).astype("int32")
    j = np.floor((lo - w) / GRID).astype("int32")
    ok = (i >= 0) & (i < len(lat)) & (j >= 0) & (j < len(lon)) & np.isfinite(lo)
    if not ok.any():
        out = None
    else:
        rr, cc = np.where(ok)
        r0, r1, c0, c1 = rr.min(), rr.max() + 1, cc.min(), cc.max() + 1
        flat = np.where(ok, i * len(lon) + j, -1)[r0:r1, c0:c1].ravel()
        total = np.bincount(flat[flat >= 0], minlength=len(lat) * len(lon))
        out = ((int(r0), int(c0), int(r1 - r0), int(c1 - c0)), flat, total)
    _geom_cache[key] = out
    return out


def _read(href: str, qa_href: str, spec: dict, bbox, lat, lon):
    """Native-resolution read of one composite tile with its quality layer.
    Returns per-cell (sum of good values, number of good pixels, pixels in cell, values present, kept)."""
    ncell = len(lat) * len(lon)
    with rasterio.open(href) as ds:
        geo = _bins(ds.transform, ds.shape, bbox, lat, lon)
        if geo is None:
            z = np.zeros(ncell)
            return z, z, z, 0, 0
        (r0, c0, h, w), flat, total = geo
        win = Window(c0, r0, w, h)
        a = ds.read(1, window=win).ravel().astype("float64")
    with rasterio.open(qa_href) as qs:
        q = qs.read(1, window=win).ravel()
    inside = flat >= 0
    present = inside & (a >= spec["vmin"]) & (a <= spec["vmax"])
    good = present & spec["qa_ok"](q)
    idx = flat[good]
    vals = a[good] * spec["scale"] + spec["offset"]
    s = np.bincount(idx, vals, ncell)
    c = np.bincount(idx, minlength=ncell).astype("float64")
    return s, c, total.astype("float64"), int(present.sum()), int(good.sum())


def _year(var_id, region_id, year, catalog, log, workers=32):
    spec = SPEC[var_id]
    reg = get_region(region_id)
    lat, lon = _grid(reg.bbox)
    ncell = len(lat) * len(lon)
    ck = RAW_DIR / "modis_qa" / f"{var_id}__{region_id}__{year}.npz"
    if ck.exists():
        z = np.load(ck)
        return z["sums"], z["counts"], z["qa"]
    search = catalog.search(collections=[spec["collection"]], bbox=list(reg.bbox),
                            datetime=f"{year}-01-01/{year}-12-31")
    items = [it for it in search.items() if it.id.startswith(spec["prefix"] + ".")]
    # composite (start date) -> list of tiles; a composite's cell mean uses all its tiles
    sums = np.zeros((12, ncell))
    counts = np.zeros((12, ncell))
    qa = np.zeros(2)              # pixels with a value in range, pixels kept by the quality test
    failures = 0
    per_comp: dict = {}
    with ThreadPoolExecutor(workers) as ex:
        futs = {}
        for it in items:
            start = pd.Timestamp(it.properties.get("start_datetime") or it.datetime)
            if start.year != year:
                continue
            futs[ex.submit(_read, it.assets[spec["asset"]].href, it.assets[spec["qa_asset"]].href,
                           spec, reg.bbox, lat, lon)] = start
        for fu in as_completed(futs):
            start = futs[fu]
            try:
                s, c, tot, n_present, n_kept = fu.result()
            except Exception as e:  # keep going; recorded as missing data
                failures += 1
                log(f"  read failed ({e!r:.120})")
                continue
            acc = per_comp.setdefault(start, [np.zeros(ncell), np.zeros(ncell), np.zeros(ncell)])
            acc[0] += s
            acc[1] += c
            acc[2] += tot
            qa += (n_present, n_kept)
    for start, (s, c, tot) in per_comp.items():
        # per-composite cell mean first, so each composite has equal weight; a cell needs enough good pixels
        have = (c > 0) & (c >= MIN_GOOD_FRACTION * tot)
        m = start.month - 1
        sums[m, have] += s[have] / c[have]
        counts[m, have] += 1
    log(f"  {var_id} {region_id} {year}: {len(futs)} granule-tiles, {failures} failed, "
        f"QA kept {qa[1] / max(qa[0], 1):.1%} of pixels with values")
    if failures <= max(2, len(futs) // 50):
        ck.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(ck, sums=sums, counts=counts, qa=qa)
    return sums, counts, qa


def fetch(var_id: str, region_id: str, log=print, years=None, progress=None):
    v, reg = VARIABLES[var_id], get_region(region_id)
    y0, y1 = years or v.years
    lat, lon = _grid(reg.bbox)
    times = month_index(y0, y1)
    vals = np.full((len(times), len(lat), len(lon)), np.nan, "float32")
    cnt = np.zeros(vals.shape, "int16")
    qa_total = np.zeros(2)
    for k, year in enumerate(range(y0, y1 + 1)):
        catalog = pystac_client.Client.open(STAC, modifier=pc.sign_inplace)  # fresh SAS tokens
        sums, counts, qa = _year(var_id, region_id, year, catalog, log)
        qa_total += qa
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = np.where(counts > 0, sums / np.maximum(counts, 1), np.nan)
        vals[k * 12:(k + 1) * 12] = mean.reshape(12, len(lat), len(lon))
        cnt[k * 12:(k + 1) * 12] = counts.reshape(12, len(lat), len(lon))
        if progress:
            progress((k + 1) / (y1 - y0 + 1), f"MODIS {year} done")
    spec = SPEC[var_id]
    return write_cube(var_id, region_id, vals, times, lat, lon, count=cnt, extra_attrs={
        "stac_api": STAC, "collection": spec["collection"], "asset": spec["asset"],
        "platform_filter": spec["prefix"] + (" (Terra only)" if spec["prefix"].startswith("MOD") else " (Aqua only)"),
        "quality_asset": spec["qa_asset"], "quality_mask": spec["qa_rule"],
        "read_resolution": "native (no overviews)", "min_good_fraction_per_cell": MIN_GOOD_FRACTION,
        "qa_pixels_with_values": int(qa_total[0]), "qa_pixels_kept": int(qa_total[1]),
        "qa_kept_share": round(float(qa_total[1] / max(qa_total[0], 1)), 4),
        "grid": "0.1 deg regular lat/lon, mean of quality-screened native pixels",
        "count_meaning": "number of composites contributing to the monthly cell value",
    })
