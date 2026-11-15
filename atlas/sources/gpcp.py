"""GPCP v2.3 monthly precipitation (satellites + GPCC rain gauges), no login required.

The Global Precipitation Climatology Project monthly analysis (NASA GSFC / University
of Maryland, archived by NOAA NCEI and served by NOAA PSL) is used as an independent
check of the MERRA-2 precipitation from NASA POWER. 2.5° grid, mm/day. We start in
1988: before the SSM/I microwave era the analysis relies on an infrared-only index
(OPI), a known break in homogeneity (Adler et al. 2018).
"""
from __future__ import annotations

import urllib.request

import numpy as np
import pandas as pd
import xarray as xr

from ..config import RAW_DIR, VARIABLES, get_region
from .common import month_index, write_cube

URL = "https://downloads.psl.noaa.gov/Datasets/gpcp/precip.mon.mean.nc"
LOCAL = RAW_DIR / "gpcp_v23_precip.mon.mean.nc"
HALF = 1.25   # half of the 2.5° cell


def ensure_raw(log=print):
    if not LOCAL.exists():
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        log(f"downloading {URL}")
        tmp = LOCAL.with_suffix(".part")
        urllib.request.urlretrieve(URL, tmp)
        tmp.replace(LOCAL)
    return LOCAL


def fetch(var_id: str, region_id: str, log=print, progress=None):
    v, reg = VARIABLES[var_id], get_region(region_id)
    w, s, e, n = reg.bbox
    y0, y1 = v.years
    with xr.open_dataset(ensure_raw(log), decode_times=False, drop_variables=["time_bnds"]) as ds:
        t = pd.Timestamp("1800-01-01") + pd.to_timedelta(ds["time"].values, "D")
        da = ds["precip"].assign_coords(time=t.values.astype("datetime64[ns]"))
        da = da.assign_coords(lon=((da.lon + 180) % 360) - 180).sortby("lon").sortby("lat")
        da = da.sel(time=slice(f"{y0}-01-01", f"{y1}-12-31"))
        # 2.5° cells that overlap the box (strictly, not just touching an edge); at least the nearest cell
        eps = 1e-3   # coordinates are float32
        sub = da.sel(lat=slice(s - HALF + eps, n + HALF - eps), lon=slice(w - HALF + eps, e + HALF - eps))
        if sub.sizes["lat"] == 0 or sub.sizes["lon"] == 0:
            sub = da.sel(lat=[(s + n) / 2], lon=[(w + e) / 2], method="nearest")
        sub = sub.load()
    times = month_index(y0, y1)
    assert sub.sizes["time"] == len(times), (sub.sizes, len(times))
    return write_cube(var_id, region_id, sub.values.astype("float32"), times, sub.lat.values, sub.lon.values,
                      extra_attrs={"source_file": URL, "version": "GPCP v2.3 monthly (final + interim)",
                                   "start_note": "starts 1988 to avoid the pre-SSM/I (OPI-only) period"})
