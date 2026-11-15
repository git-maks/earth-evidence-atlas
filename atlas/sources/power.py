"""NASA POWER monthly regional adapter (no login required).
Docs: https://power.larc.nasa.gov/docs/services/api/temporal/monthly/
"""
from __future__ import annotations

import math
import time

import httpx
import numpy as np

from ..config import VARIABLES, get_region
from .common import month_index, write_cube

API = "https://power.larc.nasa.gov/api/temporal/monthly/regional"
PARAM = {"t2m": "T2M", "precip": "PRECTOTCORR", "soil_root": "GWETROOT"}
MIN_SPAN = 2.0
MAX_SPAN = 10.0  # POWER regional requests are limited to a 10° box
FILL = -999.0


def _request_span(lo: float, hi: float, limit: float) -> tuple[float, float]:
    if hi - lo >= MIN_SPAN:
        return lo, hi
    span = MIN_SPAN + 0.01  # leave room for coordinate rounding at the 2° boundary
    start = max(-limit, min(limit - span, (lo + hi - span) / 2))
    return start, start + span


def _chunks(lo: float, hi: float):
    n = max(1, math.ceil((hi - lo) / MAX_SPAN - 1e-9))
    step = (hi - lo) / n
    return [(lo + i * step, lo + (i + 1) * step) for i in range(n)]


def _get(client: httpx.Client, params: dict) -> dict:
    for attempt in range(5):
        try:
            r = client.get(API, params=params, timeout=300)
            if r.status_code == 200:
                return r.json()
            err = r.text[:300]
            if r.status_code < 500 and r.status_code not in (408, 429):
                break  # retrying the same rejected request cannot change its bounds
        except httpx.HTTPError as e:  # network hiccup
            err = repr(e)
        if attempt < 4:
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"POWER request failed: {err}")


def _selected_axis(coords: list[float], lo: float, hi: float) -> list[float]:
    inside = [value for value in coords if lo <= value <= hi]
    return inside or [min(coords, key=lambda value: abs(value - (lo + hi) / 2))]


def fetch(var_id: str, region_id: str, log=print, progress=None):
    v, reg = VARIABLES[var_id], get_region(region_id)
    w, s, e, n = reg.bbox
    y0, y1 = v.years
    points: dict[tuple[float, float], dict] = {}
    boxes = [(a, b) for a in _chunks(*_request_span(s, n, 90)) for b in _chunks(*_request_span(w, e, 180))]
    done = 0
    with httpx.Client(headers={"User-Agent": "earth-evidence-atlas/0.1"}) as client:
        for (la0, la1), (lo0, lo1) in boxes:
            params = {"latitude-min": la0, "latitude-max": la1, "longitude-min": lo0,
                      "longitude-max": lo1, "parameters": PARAM[var_id], "community": "AG",
                      "start": y0, "end": y1, "format": "json"}
            log(f"POWER {PARAM[var_id]} {region_id} box lat {la0:.1f}-{la1:.1f} lon {lo0:.1f}-{lo1:.1f}")
            js = _get(client, params)
            for f in js["features"]:
                lon, lat = f["geometry"]["coordinates"][:2]
                points[(round(lat, 4), round(lon, 4))] = f["properties"]["parameter"][PARAM[var_id]]
            done += 1
            if progress:
                progress(done / len(boxes), f"POWER box {done}/{len(boxes)}")
    if not points:
        raise RuntimeError("POWER returned no grid cells for the requested area")
    lats = _selected_axis(sorted({p[0] for p in points}), s, n)
    lons = _selected_axis(sorted({p[1] for p in points}), w, e)
    times = month_index(y0, y1)
    keys = [f"{t.year}{t.month:02d}" for t in times]
    arr = np.full((len(times), len(lats), len(lons)), np.nan, "float32")
    li = {x: i for i, x in enumerate(lats)}
    lj = {x: j for j, x in enumerate(lons)}
    for (la, lo), series in points.items():
        if la not in li or lo not in lj:
            continue  # only the download is padded, not the analysis grid
        vals = np.array([series.get(k, FILL) for k in keys], "float32")
        vals[vals <= FILL + 1] = np.nan
        arr[:, li[la], lj[lo]] = vals
    return write_cube(var_id, region_id, arr, times, lats, lons,
                      extra_attrs={"api": API, "parameter": PARAM[var_id], "grid": "0.5 x 0.625 deg (MERRA-2)"})
