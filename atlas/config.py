"""Catalogue of variables and regions used by Earth Evidence Atlas."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CUBE_DIR = DATA_DIR / "cubes"
RAW_DIR = DATA_DIR / "raw"


@dataclass(frozen=True)
class Region:
    id: str
    name: str
    bbox: tuple[float, float, float, float]  # west, south, east, north
    story: str


@dataclass(frozen=True)
class Variable:
    id: str
    name: str
    question: str          # beginner-friendly question shown in the UI
    definition: str        # one-sentence plain-language definition
    units: str             # units of the stored values
    trend_units: str       # units of the slope shown to users
    source: str            # adapter id
    product: str           # product short name / version
    provider: str
    kind: str              # "satellite observation" | "reanalysis model" | "station-based analysis"
    resolution: str
    years: tuple[int, int]  # complete years kept in the cube
    regions: tuple[str, ...]
    citation: str
    url: str
    license: str
    caveats: tuple[str, ...] = field(default_factory=tuple)
    colormap: str = "RdBu_r"   # diverging map for trend; "BrBG" for wet/green good

    def public(self) -> dict:
        return asdict(self)


REGIONS: dict[str, Region] = {
    r.id: r
    for r in [
        Region(
            "central_europe",
            "Central Europe (Poland and neighbours)",
            (14.0, 49.0, 24.0, 55.0),
            "Do hot recent years make a trend?",
        ),
        Region(
            "nw_india",
            "North-west India (Punjab, Haryana, Rajasthan)",
            (72.0, 26.0, 78.0, 31.0),
            "Greener fields, but more water?",
        ),
        Region(
            "amazon_arc",
            "Southern Amazon 'arc of deforestation' (Rondônia, Mato Grosso)",
            (-64.0, -13.0, -54.0, -7.0),
            "Forest loss changes heat and green.",
        ),
        Region(
            "world",
            "Whole world",
            (-180.0, -90.0, 180.0, 90.0),
            "Where did it warm fastest?",
        ),
    ]
}

PRESET = ("central_europe", "nw_india", "amazon_arc")

VARIABLES: dict[str, Variable] = {
    v.id: v
    for v in [
        Variable(
            id="ndvi",
            name="Vegetation greenness (NDVI)",
            question="Greener or browner?",
            definition="NDVI compares red and near-infrared light reflected by plants; higher values mean denser, healthier green vegetation (−0.2 water/bare … 0.9 dense forest).",
            units="NDVI (unitless)",
            trend_units="NDVI per decade",
            source="modis_pc",
            product="MOD13A1 v061 (Terra, 16-day, 500 m)",
            provider="NASA LP DAAC; COG mirror on Microsoft Planetary Computer",
            kind="satellite observation",
            resolution="500 m product, averaged to 0.1° grid (≈ 8–11 km)",
            years=(2001, 2024),
            regions=PRESET,
            citation="Didan, K. (2021). MODIS/Terra Vegetation Indices 16-Day L3 Global 500m SIN Grid V061. NASA EOSDIS LP DAAC. doi:10.5067/MODIS/MOD13A1.061",
            url="https://doi.org/10.5067/MODIS/MOD13A1.061",
            license="NASA EOSDIS data: no restrictions on reuse (NASA Earth Science Data Policy)",
            caveats=(
                "Monthly value = mean of 16-day composites starting in that month, read from 8× COG overviews (≈ 4 km) before averaging to 0.1°.",
                "The per-pixel quality layer is not applied in this prototype; values outside the valid range are removed.",
                "Terra's orbit drifted after 2022; the default period stops at 2024.",
                "A change in NDVI can come from land-use change (clearing, irrigation), not only from climate.",
            ),
            colormap="BrBG",
        ),
        Variable(
            id="lst_day",
            name="Daytime land surface temperature",
            question="Hotter ground by day?",
            definition="How hot the ground/canopy surface is around 10:30 local time, measured from space in clear-sky conditions – not the air temperature you feel.",
            units="°C",
            trend_units="°C per decade",
            source="modis_pc",
            product="MOD11A2 v061 (Terra, 8-day, 1 km)",
            provider="NASA LP DAAC; COG mirror on Microsoft Planetary Computer",
            kind="satellite observation",
            resolution="1 km product, averaged to 0.1° grid (≈ 8–11 km)",
            years=(2001, 2024),
            regions=PRESET,
            citation="Wan, Z., Hook, S., Hulley, G. (2021). MODIS/Terra Land Surface Temperature/Emissivity 8-Day L3 Global 1km SIN Grid V061. NASA EOSDIS LP DAAC. doi:10.5067/MODIS/MOD11A2.061",
            url="https://doi.org/10.5067/MODIS/MOD11A2.061",
            license="NASA EOSDIS data: no restrictions on reuse (NASA Earth Science Data Policy)",
            caveats=(
                "Only clear-sky observations exist: cloudy months contribute fewer values (see coverage).",
                "Monthly value = mean of 8-day composites starting in that month, read from 4× COG overviews (≈ 4 km).",
                "Terra's overpass time drifted after 2022; the default period stops at 2024.",
            ),
        ),
        Variable(
            id="lst_day_aqua",
            name="Afternoon land surface temperature (Aqua)",
            question="Does a second satellite agree?",
            definition="Same measurement as the Terra daytime surface temperature, but from the Aqua satellite passing around 13:30 local time; its orbit was kept stable until 2022, so it is a useful cross-check.",
            units="°C",
            trend_units="°C per decade",
            source="modis_pc",
            product="MYD11A2 v061 (Aqua, 8-day, 1 km)",
            provider="NASA LP DAAC; COG mirror on Microsoft Planetary Computer",
            kind="satellite observation",
            resolution="1 km product, averaged to 0.1° grid (≈ 8–11 km)",
            years=(2003, 2024),
            regions=PRESET,
            citation="Wan, Z., Hook, S., Hulley, G. (2021). MODIS/Aqua Land Surface Temperature/Emissivity 8-Day L3 Global 1km SIN Grid V061. NASA EOSDIS LP DAAC. doi:10.5067/MODIS/MYD11A2.061",
            url="https://doi.org/10.5067/MODIS/MYD11A2.061",
            license="NASA EOSDIS data: no restrictions on reuse (NASA Earth Science Data Policy)",
            caveats=(
                "Aqua starts in mid-2002; the cube starts in 2003 (first complete year).",
                "Afternoon surface temperature differs from morning (Terra) values; compare trends, not levels.",
                "Aqua's orbit also began drifting after 2022.",
            ),
        ),
        Variable(
            id="t2m",
            name="Air temperature at 2 m",
            question="Warmer air?",
            definition="Monthly mean air temperature two metres above the ground, from the NASA MERRA-2 reanalysis (a model that assimilates observations).",
            units="°C",
            trend_units="°C per decade",
            source="power",
            product="NASA POWER monthly T2M (MERRA-2)",
            provider="NASA Langley Research Center POWER Project",
            kind="reanalysis model",
            resolution="0.5° × 0.625° (≈ 50 km)",
            years=(1981, 2025),
            regions=PRESET,
            citation="NASA Langley Research Center (LaRC) POWER Project, funded through the NASA Earth Science/Applied Science Program; MERRA-2 (Gelaro et al., 2017, J. Climate).",
            url="https://power.larc.nasa.gov/",
            license="NASA POWER data: free to use, acknowledgement requested",
            caveats=("Reanalysis = model constrained by observations; not a direct satellite measurement.",),
        ),
        Variable(
            id="precip",
            name="Precipitation",
            question="More or less rain?",
            definition="Average amount of rain and snow reaching the ground per day, from MERRA-2 corrected with observed precipitation.",
            units="mm/day",
            trend_units="mm/day per decade",
            source="power",
            product="NASA POWER monthly PRECTOTCORR (MERRA-2, bias-corrected)",
            provider="NASA Langley Research Center POWER Project",
            kind="reanalysis model",
            resolution="0.5° × 0.625° (≈ 50 km)",
            years=(1981, 2025),
            regions=PRESET,
            citation="NASA Langley Research Center (LaRC) POWER Project; MERRA-2 bias-corrected precipitation (Reichle et al., 2017).",
            url="https://power.larc.nasa.gov/",
            license="NASA POWER data: free to use, acknowledgement requested",
            caveats=(
                "Precipitation varies a lot year to year: long periods are needed before a trend is detectable.",
                "Planned upgrade: GPM IMERG monthly (needs NASA Earthdata Login).",
            ),
            colormap="BrBG",
        ),
        Variable(
            id="soil_root",
            name="Root-zone soil wetness",
            question="Drier or wetter soil?",
            definition="How full the soil water store is in the root zone (top ~1 m): 0 = completely dry, 1 = saturated. Modelled by MERRA-2.",
            units="fraction (0–1)",
            trend_units="fraction per decade",
            source="power",
            product="NASA POWER monthly GWETROOT (MERRA-2)",
            provider="NASA Langley Research Center POWER Project",
            kind="reanalysis model",
            resolution="0.5° × 0.625° (≈ 50 km)",
            years=(1981, 2025),
            regions=PRESET,
            citation="NASA Langley Research Center (LaRC) POWER Project; MERRA-2 land surface (Reichle et al., 2017).",
            url="https://power.larc.nasa.gov/",
            license="NASA POWER data: free to use, acknowledgement requested",
            caveats=(
                "Model estimate: irrigation and groundwater pumping are not represented.",
                "Planned independent check: SMAP (2015–) or GRACE water storage (needs Earthdata Login).",
            ),
            colormap="BrBG",
        ),
        Variable(
            id="gistemp",
            name="Surface temperature anomaly (GISTEMP v4)",
            question="Where is it warming fastest?",
            definition="Difference between the monthly surface temperature and its 1951–1980 average, combining weather stations on land and ships/buoys at sea.",
            units="°C (anomaly vs 1951–1980)",
            trend_units="°C per decade",
            source="gistemp",
            product="GISTEMP v4, 1200 km smoothing, GHCNv4 + ERSSTv5",
            provider="NASA Goddard Institute for Space Studies",
            kind="station-based analysis",
            resolution="2° × 2° (≈ 220 km)",
            years=(1951, 2025),
            regions=("world",) + PRESET,
            citation="GISTEMP Team (2026). GISS Surface Temperature Analysis (GISTEMP), version 4. NASA GISS. Lenssen et al. (2019, 2024).",
            url="https://data.giss.nasa.gov/gistemp/",
            license="NASA GISS data: free to use with citation",
            caveats=(
                "Grid cells far from stations are filled from neighbours up to 1200 km away; polar and early-period values are less certain.",
                "Small regions contain only a few 2° cells.",
            ),
        ),
    ]
}


CUSTOM_FILE = DATA_DIR / "custom_regions.json"


def custom_regions() -> dict[str, Region]:
    import json
    if not CUSTOM_FILE.exists():
        return {}
    raw = json.loads(CUSTOM_FILE.read_text())
    return {k: Region(k, v["name"], tuple(v["bbox"]), v.get("story", "Area picked on the globe.")) for k, v in raw.items()}


def touch_custom_region(region_id: str, min_gap_s: float = 3600) -> None:
    """Remember when a user-made area was last used (for optional clean-up on a public server)."""
    import json
    import time
    if not region_id.startswith("c_") or not CUSTOM_FILE.exists():
        return
    raw = json.loads(CUSTOM_FILE.read_text())
    if region_id in raw and time.time() - raw[region_id].get("used", 0) > min_gap_s:
        raw[region_id]["used"] = time.time()
        CUSTOM_FILE.write_text(json.dumps(raw, indent=1))


def prune_custom_regions(max_age_days: float, max_count: int) -> list[str]:
    """Delete user-made areas not used for max_age_days, and the oldest ones above max_count.
    Removes their cubes and download checkpoints. Built-in regions are never touched.
    Only runs when the server is started with ATLAS_PRUNE_DAYS / ATLAS_MAX_CUSTOM set (see api.py)."""
    import json
    import time
    if not CUSTOM_FILE.exists():
        return []
    raw = json.loads(CUSTOM_FILE.read_text())
    now = time.time()
    for v in raw.values():  # areas from before timestamps existed count as used now
        v.setdefault("used", now)
    order = sorted(raw, key=lambda k: raw[k]["used"], reverse=True)
    drop = [k for i, k in enumerate(order) if now - raw[k]["used"] > max_age_days * 86400 or i >= max_count]
    for k in drop:
        raw.pop(k)
        for f in list(CUBE_DIR.glob(f"*__{k}.nc")) + list((DATA_DIR / "raw" / "modis").glob(f"*__{k}__*.npz")):
            f.unlink(missing_ok=True)
    CUSTOM_FILE.write_text(json.dumps(raw, indent=1))
    return drop


def add_custom_region(bbox: tuple[float, float, float, float], name: str | None = None) -> Region:
    import hashlib
    import json
    bbox = tuple(round(float(x), 2) for x in bbox)
    rid = "c_" + hashlib.sha1(repr(bbox).encode()).hexdigest()[:10]
    raw = json.loads(CUSTOM_FILE.read_text()) if CUSTOM_FILE.exists() else {}
    if rid not in raw:
        w, s, e, n = bbox
        raw[rid] = {"name": name or f"Custom area {abs(s):.1f}°{'S' if s < 0 else 'N'}–{abs(n):.1f}°{'S' if n < 0 else 'N'}, "
                                     f"{abs(w):.1f}°{'W' if w < 0 else 'E'}–{abs(e):.1f}°{'W' if e < 0 else 'E'}",
                    "bbox": list(bbox), "created": __import__("time").time(), "used": __import__("time").time()}
        CUSTOM_FILE.parent.mkdir(parents=True, exist_ok=True)
        CUSTOM_FILE.write_text(json.dumps(raw, indent=1))
    return custom_regions()[rid]


def get_region(region_id: str) -> Region | None:
    return REGIONS.get(region_id) or custom_regions().get(region_id)


def cube_path(var_id: str, region_id: str) -> Path:
    return CUBE_DIR / f"{var_id}__{region_id}.nc"
