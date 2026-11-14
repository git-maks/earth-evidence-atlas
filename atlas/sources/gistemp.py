"""NASA GISTEMP v4 gridded anomalies (no login required).

AI-generated with Claude; team review pending.
"""
from __future__ import annotations

import gzip
import shutil
import urllib.request

import numpy as np
import xarray as xr

from ..config import RAW_DIR, VARIABLES, get_region
from .common import month_index, write_cube

URL = "https://data.giss.nasa.gov/pub/gistemp/gistemp1200_GHCNv4_ERSSTv5.nc.gz"
LOCAL = RAW_DIR / "gistemp1200_GHCNv4_ERSSTv5.nc"


def ensure_raw(log=print):
    if not LOCAL.exists():
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        gz = LOCAL.with_suffix(".nc.gz")
        log(f"downloading {URL}")
        urllib.request.urlretrieve(URL, gz)
        with gzip.open(gz) as src, open(LOCAL, "wb") as dst:
            shutil.copyfileobj(src, dst)
    return LOCAL


def fetch(var_id: str, region_id: str, log=print, progress=None):
    v, reg = VARIABLES[var_id], get_region(region_id)
    w, s, e, n = reg.bbox
    y0, y1 = v.years
    with xr.open_dataset(ensure_raw(log)) as ds:
        da = ds["tempanomaly"].sel(time=slice(f"{y0}-01-01", f"{y1}-12-31"))
        # 2° cells whose centre lies in the box; at least one cell for small boxes
        da = da.sel(lat=slice(s - 1, n + 1), lon=slice(w - 1, e + 1)).load()
    times = month_index(y0, y1)
    assert da.sizes["time"] == len(times), (da.sizes, len(times))
    vals = da.values.astype("float32")
    return write_cube(var_id, region_id, vals, times, da.lat.values, da.lon.values,
                      extra_attrs={"source_file": URL, "baseline": "1951-1980"})
