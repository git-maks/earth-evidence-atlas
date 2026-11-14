"""Build all data cubes. Usage: python -m scripts.build_data [var ...] [--region r]

AI-generated with Claude; team review pending.
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback

from atlas.config import VARIABLES, cube_path
from atlas.sources import gistemp, modis_pc, power

ADAPTERS = {"power": power.fetch, "gistemp": gistemp.fetch, "modis_pc": modis_pc.fetch}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("vars", nargs="*", default=list(VARIABLES))
    ap.add_argument("--region", action="append")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    ok = True
    for vid in a.vars:
        v = VARIABLES[vid]
        for rid in (a.region or v.regions):
            if rid not in v.regions:
                continue
            if cube_path(vid, rid).exists() and not a.force:
                print(f"skip {vid}/{rid} (exists)", flush=True)
                continue
            t = time.time()
            try:
                ds = ADAPTERS[v.source](vid, rid, log=lambda m: print(m, flush=True))
                print(f"done {vid}/{rid} {dict(ds.sizes)} in {time.time()-t:.0f}s", flush=True)
            except Exception:
                ok = False
                traceback.print_exc()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
