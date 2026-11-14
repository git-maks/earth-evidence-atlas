"""MODIS Terra (MOD13A1 NDVI, MOD11A2 LST) via Microsoft Planetary Computer COGs.

No NASA Earthdata Login needed: the Planetary Computer mirrors the NASA LP DAAC
v061 products as cloud-optimised GeoTIFFs with internal overviews. We read a
coarse overview (~4 km) of every composite, convert sinusoidal pixel centres to
lat/lon, and average them into a regular 0.1° grid and calendar months.

AI-generated with Claude; team review pending.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

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

SPEC = {
    "ndvi": dict(collection="modis-13A1-061", prefix="MOD13A1", asset="500m_16_days_NDVI",
                 factor=8, vmin=-2000, vmax=10000, scale=1e-4, offset=0.0),
    "lst_day_aqua": dict(collection="modis-11A2-061", prefix="MYD11A2", asset="LST_Day_1km",
                         factor=4, vmin=7500, vmax=65535, scale=0.02, offset=-273.15),
    "lst_day": dict(collection="modis-11A2-061", prefix="MOD11A2", asset="LST_Day_1km",
                    factor=4, vmin=7500, vmax=65535, scale=0.02, offset=-273.15),
}

_geom_cache: dict = {}


def _grid(bbox):
    w, s, e, n = bbox
    lat = np.round(np.arange(s + GRID / 2, n, GRID), 4)
    lon = np.round(np.arange(w + GRID / 2, e, GRID), 4)
    return lat, lon


def _bins(transform, shape, bbox, lat, lon):
    """Flat 0.1° bin index for every overview pixel (-1 = outside box)."""
    key = (tuple(transform), shape, bbox)
    if key in _geom_cache:
        return _geom_cache[key]
    rows, cols = np.mgrid[0:shape[0], 0:shape[1]]
    x = transform.c + (cols + 0.5) * transform.a
    y = transform.f + (rows + 0.5) * transform.e
    la = np.degrees(y / R_SPHERE)
    with np.errstate(divide="ignore", invalid="ignore"):
        lo = np.degrees(x / (R_SPHERE * np.cos(np.radians(la))))
    w, s, e, n = bbox
    i = np.floor((la - s) / GRID).astype(int)
    j = np.floor((lo - w) / GRID).astype(int)
    ok = (i >= 0) & (i < len(lat)) & (j >= 0) & (j < len(lon)) & np.isfinite(lo)
    flat = np.where(ok, i * len(lon) + j, -1).ravel()
    _geom_cache[key] = flat
    return flat


def _read(href: str, spec: dict, bbox, lat, lon):
    with rasterio.open(href) as ds:
        f = spec["factor"]
        out_shape = (ds.height // f, ds.width // f)
        arr = ds.read(1, out_shape=out_shape)
        tr = ds.transform * ds.transform.scale(ds.width / out_shape[1], ds.height / out_shape[0])
    flat = _bins(tr, out_shape, bbox, lat, lon)
    a = arr.ravel().astype("float64")
    good = (flat >= 0) & (a >= spec["vmin"]) & (a <= spec["vmax"])
    return flat[good], a[good] * spec["scale"] + spec["offset"]


def _year(var_id, region_id, year, catalog, log, workers=32):
    spec = SPEC[var_id]
    reg = get_region(region_id)
    lat, lon = _grid(reg.bbox)
    ncell = len(lat) * len(lon)
    ck = RAW_DIR / "modis" / f"{var_id}__{region_id}__{year}.npz"
    if ck.exists():
        z = np.load(ck)
        return z["sums"], z["counts"]
    search = catalog.search(collections=[spec["collection"]], bbox=list(reg.bbox),
                            datetime=f"{year}-01-01/{year}-12-31")
    items = [it for it in search.items() if it.id.startswith(spec["prefix"] + ".")]
    sums = np.zeros((12, ncell))
    counts = np.zeros((12, ncell))
    failures = 0
    with ThreadPoolExecutor(workers) as ex:
        futs = {}
        for it in items:
            start = pd.Timestamp(it.properties.get("start_datetime") or it.datetime)
            if start.year != year:
                continue
            futs[ex.submit(_read, it.assets[spec["asset"]].href, spec, reg.bbox, lat, lon)] = start.month - 1
        for fu in as_completed(futs):
            m = futs[fu]
            try:
                idx, vals = fu.result()
            except Exception as e:  # keep going; recorded as missing data
                failures += 1
                log(f"  read failed ({e!r:.120})")
                continue
            # per-composite cell mean first, so each composite has equal weight
            s = np.bincount(idx, vals, ncell)
            c = np.bincount(idx, minlength=ncell)
            have = c > 0
            sums[m, have] += s[have] / c[have]
            counts[m, have] += 1
    log(f"  {var_id} {region_id} {year}: {len(futs)} granule-tiles, {failures} failed")
    if failures <= max(2, len(futs) // 50):
        ck.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(ck, sums=sums, counts=counts)
    return sums, counts


def fetch(var_id: str, region_id: str, log=print, years=None, progress=None):
    v, reg = VARIABLES[var_id], get_region(region_id)
    y0, y1 = years or v.years
    lat, lon = _grid(reg.bbox)
    times = month_index(y0, y1)
    vals = np.full((len(times), len(lat), len(lon)), np.nan, "float32")
    cnt = np.zeros(vals.shape, "int16")
    for k, year in enumerate(range(y0, y1 + 1)):
        catalog = pystac_client.Client.open(STAC, modifier=pc.sign_inplace)  # fresh SAS tokens
        sums, counts = _year(var_id, region_id, year, catalog, log)
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
        "overview_factor": spec["factor"], "grid": "0.1 deg regular lat/lon, cell mean of overview pixels",
        "count_meaning": "number of composites contributing to the monthly cell value",
    })
