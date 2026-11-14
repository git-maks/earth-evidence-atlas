"""Helpers shared by data adapters (AI-generated with Claude; team review pending)."""
from __future__ import annotations

import datetime as dt
import json
import threading

import numpy as np
import pandas as pd
import xarray as xr

from ..config import VARIABLES, cube_path

# netCDF4/HDF5 is not thread-safe: every read or write of a cube file holds this lock
IO_LOCK = threading.RLock()


def month_index(y0: int, y1: int) -> pd.DatetimeIndex:
    return pd.date_range(f"{y0}-01-01", f"{y1}-12-01", freq="MS")


def write_cube(var_id: str, region_id: str, values: np.ndarray, times, lat, lon,
               count: np.ndarray | None = None, extra_attrs: dict | None = None) -> xr.Dataset:
    v = VARIABLES[var_id]
    data_vars = {"value": (("time", "lat", "lon"), values.astype("float32"))}
    if count is not None:
        data_vars["count"] = (("time", "lat", "lon"), count.astype("int16"))
    ds = xr.Dataset(data_vars, coords={"time": times, "lat": np.asarray(lat, "float64"),
                                       "lon": np.asarray(lon, "float64")})
    ds["value"].attrs["units"] = v.units
    ds.attrs.update({
        "variable": var_id, "region": region_id, "product": v.product,
        "provider": v.provider, "citation": v.citation, "source_url": v.url,
        "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "generator": "Earth Evidence Atlas pipeline (code generated with Claude/Anthropic AI assistant)",
    })
    if extra_attrs:
        ds.attrs.update({k: (json.dumps(x) if isinstance(x, (dict, list)) else x) for k, x in extra_attrs.items()})
    path = cube_path(var_id, region_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.nc")
    enc = {k: {"zlib": True, "complevel": 4} for k in data_vars}
    with IO_LOCK:
        ds.to_netcdf(tmp, encoding=enc)
        tmp.replace(path)
    return ds
