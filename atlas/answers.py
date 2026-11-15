"""Plain-language answers to the Detective questions, built only from the computed results.
No language model is used at run time: every sentence is a fixed template filled with numbers
from the analysis (trend, confidence interval, tests, robustness matrix, trend map), so each claim
can be checked on the charts and in the JSON export. The answers never name causes.
"""
from __future__ import annotations

import math

import numpy as np

SEASON = {(12, 1, 2): "winter (Dec–Feb)", (3, 4, 5): "spring (Mar–May)", (6, 7, 8): "summer (Jun–Aug)",
          (9, 10, 11): "autumn (Sep–Nov)"}

# How each question is answered. yes_if_up: the question is a yes/no question where "up" means "yes".
PHRASES = {
    "ndvi": dict(subject="Vegetation", up="greener", down="browner", yes_if_up=None, relative=True, caveat=3),
    "lst_day": dict(subject="The ground by day", up="hotter", down="cooler", yes_if_up=True, relative=False, caveat=0),
    "lst_day_aqua": dict(subject="Afternoon ground temperature", up="hotter", down="cooler", yes_if_up=None,
                         relative=False, caveat=1, compare_with="lst_day",
                         compare_label="the morning satellite (Terra)"),
    "t2m": dict(subject="The air", up="warmer", down="cooler", yes_if_up=True, relative=False, caveat=0),
    "precip": dict(subject="Rain and snow", up="more", down="less", yes_if_up=None, relative=True, caveat=0,
                   more_less=True),
    "precip_gpcp": dict(subject="Rain and snow", up="more", down="less", yes_if_up=None, relative=True, caveat=0,
                        more_less=True),
    "soil_root": dict(subject="Root-zone soil", up="wetter", down="drier", yes_if_up=None, relative=True, caveat=0),
    "gistemp": dict(subject="Surface temperature", up="warmer", down="cooler", yes_if_up=None, relative=False,
                    caveat=0, fastest=True),
}


def num(x: float | None, digits: int = 3, sign: bool = True) -> str:
    """Rounded number for text, e.g. +0.512 or -1.2."""
    if x is None or not math.isfinite(x):
        return "n/a"
    if x == 0:
        return "0"
    v = float(f"{x:.{digits}g}")
    s = f"{v:,.6f}".rstrip("0").rstrip(".") if abs(v) < 1000 else f"{v:,.0f}"
    return ("+" + s) if sign and v > 0 else s


def season_text(months: list[int]) -> str:
    if len(months) == 12:
        return "all year"
    return SEASON.get(tuple(months), "selected months")


def place_text(region_name: str, bbox_selected: bool) -> str:
    if bbox_selected:
        return "the selected area"
    name = region_name.split(" (")[0]
    return "the whole world" if name.lower() == "whole world" else name


def _direction(ph: dict, slope: float) -> str:
    return ph["up"] if slope > 0 else ph["down"]


def _headline(ph: dict, code: str, slope: float, rob: dict | None) -> str:
    d = _direction(ph, slope)
    if code == "insufficient_data":
        return "Not enough data to say."
    if code == "ci_includes_zero":
        return "We can't tell yet."
    if code == "depends_on_period":
        return "It depends on the period."
    if code == "significance_depends_on_period":
        return "Same direction, but not always significant."
    if ph.get("fastest"):
        return "Warming." if slope > 0 else "Cooling."
    if ph.get("yes_if_up") is not None:
        yes = (slope > 0) == ph["yes_if_up"]
        return f"Yes – {d}." if yes else f"No – {d}."
    if ph.get("more_less"):
        return f"{d.capitalize()}."
    return f"{d.capitalize()}."


def _main_sentence(ph: dict, code: str, a: dict, where: str, units: str) -> str:
    r = a["result"]
    slope, period = r["slope"], f"{a['start']}–{a['end']}"
    season = season_text(a["months"])
    when = f"{period}, {season}" if season != "all year" else period
    d = _direction(ph, slope)
    verb_subject = ph["subject"]
    change = f"{num(slope)} {units}"
    if code == "insufficient_data":
        return (f"Too many months are missing in {where} for {when} "
                f"(valid data {round(100 * r['valid_fraction'])}%). Try a longer period or a bigger area.")
    if code == "ci_includes_zero":
        return (f"{verb_subject} in {where} changed by {change} ({when}), but the likely range "
                f"({num(r['ci_low'])} to {num(r['ci_high'])}) includes zero. That is not proof of no change, "
                f"only that this period cannot show one.")
    if ph.get("more_less"):
        core = f"{d.capitalize()} {verb_subject.lower()} fell in {where}: {change} ({when})."
    else:
        core = f"{verb_subject} in {where} got {d}: {change} ({when})."
    if code == "depends_on_period":
        rob = a["verdict"].get("robustness") or {}
        core += (f" But only {rob.get('same_sign', '?')} of {rob.get('windows', '?')} other start/end periods "
                 f"point the same way, so the direction is not settled.")
    if code == "significance_depends_on_period":
        rob = a["verdict"].get("robustness") or {}
        core += (f" The direction holds in {rob.get('same_sign', '?')} of {rob.get('windows', '?')} other start/end "
                 f"periods, but only {rob.get('long_significant', '?')} of the {rob.get('long_windows', '?')} periods "
                 f"covering at least three quarters of this one are significant, so the result depends on the exact "
                 f"start and end years.")
    return core


def _size_sentence(ph: dict, a: dict, units_short: str) -> str | None:
    """Total change vs. the usual year-to-year swing, and as % of the usual level where that makes sense."""
    r, s = a["result"], a["series"]
    years = a["end"] - a["start"] + 1
    total = r["slope"] * years / 10
    an = np.asarray([np.nan if v is None else v for v in s["anomaly"]], dtype=float)
    yrs = np.array([int(d[:4]) for d in s["dates"]])
    annual = np.array([np.nanmean(an[yrs == y]) for y in np.unique(yrs) if np.isfinite(an[yrs == y]).any()])
    if annual.size < 5:
        return None
    swing = float(np.nanstd(annual, ddof=1))
    parts = [f"Over {years} years that adds up to about {num(total, 2)} {units_short}"]
    if swing > 0:
        ratio = abs(total) / swing
        parts.append(f"{ratio:.1f}× the usual year-to-year swing (±{num(swing, 2, sign=False)} {units_short})")
    txt = ", ".join(parts)
    if ph.get("relative"):
        absl = np.asarray([np.nan if v is None else v for v in (s.get("absolute") if s.get("absolute") is not None else [])], dtype=float)
        level = float(np.nanmean(absl)) if np.isfinite(absl).any() else None
        if level is not None and abs(level) > 1e-9:
            txt += f", or {num(100 * total / level, 2)}% of the usual level"
    return txt + "."


def _where_sentence(ph: dict, m: dict | None, a: dict, bbox_selected: bool, units: str) -> str | None:
    if bbox_selected or not m:
        return f"Based on {a['cells']} grid cells in the selected area." if bbox_selected else None
    S = m["summary"]
    n = S["cells_with_trend"]
    if not n:
        return None
    up_share = round(100 * S["positive"] / n)
    sig_share = round(100 * S["significant_fdr"] / n)
    txt = (f"Across the map, {up_share}% of grid cells went up and {100 - up_share}% went down; "
           f"{sig_share}% show a significant trend after correcting for many tests.")
    if ph.get("fastest") or ph.get("caveat") is not None:
        slope = np.asarray(m["slope"], dtype=float)
        sig = np.asarray(m["sig_fdr"], dtype=bool)
        if ph.get("fastest") and np.isfinite(slope).any():
            pick = np.where(sig, slope, np.nan) if sig.any() else slope
            i, j = np.unravel_index(np.nanargmax(pick), pick.shape)
            la, lo = float(m["lat"][i]), float(m["lon"][j])
            txt += (f" Fastest warming: around {abs(la):.0f}°{'N' if la >= 0 else 'S'}, "
                    f"{abs(lo):.0f}°{'E' if lo >= 0 else 'W'}, {num(float(slope[i, j]))} {units}.")
    return txt


def _confidence_sentence(a: dict) -> str | None:
    r, ver = a["result"], a["verdict"]
    bits = []
    rob = ver.get("robustness")
    if rob:
        if rob.get("same_sign_significant") is not None:
            bits.append(f"{rob['same_sign']} of {rob['windows']} other start/end periods give the same direction, "
                        f"{rob['same_sign_significant']} of them also significant")
        else:
            bits.append(f"{rob['same_sign']} of {rob['windows']} other start/end periods give the same direction")
    if r.get("mk_p") is not None and r.get("p") is not None and ver["code"] in SIGNIFICANT_CODES:
        bits.append("a rank-based test (Mann–Kendall) gives the same result" if r["mk_p"] < 0.05 else
                    "the rank-based Mann–Kendall test does not reach 5%")
    return ("How sure: " + "; ".join(bits) + ".") if bits else None


CROSS_LABELS = {
    "gistemp": "NASA GISTEMP (weather stations)",
    "t2m": "MERRA-2 air temperature (reanalysis)",
    "precip_gpcp": "GPCP (satellites and rain gauges)",
    "precip": "MERRA-2 rainfall (reanalysis)",
    "lst_day_aqua": "the Aqua satellite (afternoon pass)",
}
CROSS_CONCLUSIONS = {
    "agree": "Both show a significant trend in the same direction; the difference in size is not significant.",
    "same_direction_different_size": "Both show a significant trend in the same direction, but the sizes differ significantly.",
    "one_significant": "Same direction, but only one of them is significant.",
    "neither_significant": "Same direction, but neither is significant.",
    "disagree": "They disagree on the direction – treat the result with care.",
    "unclear": "Different directions, and neither is clearly significant.",
}
SIZES_DIFFER = "The two records also change by significantly different amounts."


def cross_check_line(cc: dict | None) -> str | None:
    """One sentence comparing the result with an independent dataset for the same area and years."""
    if not cc:
        return None
    label = CROSS_LABELS.get(cc["variable"], cc["name"])
    return (f"Independent check with {label}, same area, {cc['start']}–{cc['end']}: {num(cc['slope'])} "
            f"{cc['trend_units']}; this dataset gives {num(cc['main_slope'])} for the same years. "
            f"{CROSS_CONCLUSIONS[cc['agreement']]}"
            + (f" {SIZES_DIFFER}" if cc.get("sizes_differ") and cc["agreement"] in ("one_significant", "neither_significant",
                                                                                  "disagree", "unclear") else ""))


SIGNIFICANT_CODES = ("trend_detected", "depends_on_period", "significance_depends_on_period")
SHORT_RECORD = ("Short record (under 15 years): slow natural swings lasting several years can look like a trend "
                "over a period this short.")


def _significant(a: dict) -> bool:
    p = a.get("result", {}).get("p")
    return a.get("verdict", {}).get("code") in SIGNIFICANT_CODES and p is not None and p < 0.05


def p_text(p: float | None) -> str:
    if p is None or not math.isfinite(p):
        return "p n/a"
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def _how(a: dict) -> list[str]:
    r = a["result"]
    n_eff = round(r["n_eff"]) if r.get("n_eff") is not None and math.isfinite(r["n_eff"]) else "?"
    n_year = r.get("n_year")
    memory = (f"{p_text(r['p'])}, the stricter of two memory corrections: month to month (effective n ≈ {n_eff} "
              f"of {r['n']} months) and year to year ({n_year} yearly means)."
              if n_year and r.get("p_year") is not None and math.isfinite(r["p_year"]) else
              f"{p_text(r['p'])} after correcting for month-to-month memory (effective n ≈ {n_eff} of {r['n']} months).")
    return [
        f"Trend {num(r['slope'])} {a['trend_units']}, 95% range {num(r['ci_low'])} to {num(r['ci_high'])}.",
        memory,
        f"Mann–Kendall {p_text(r['mk_p'])}, also corrected for memory; Sen slope {num(r['sen_slope'])}.",
        f"Monthly values minus the usual value for each calendar month; {round(100 * r['valid_fraction'])}% valid data.",
    ]


def build(var: dict, region_name: str, a: dict, trend_map: dict | None = None, compare: dict | None = None,
          compare_var: dict | None = None) -> dict:
    """var: Variable.public(); a: analysis dict (result, verdict, series, ...); trend_map: /api/map dict for
    the whole region (None when a sub-area is selected); compare: analysis of a second dataset (Aqua vs Terra)."""
    ph = PHRASES.get(var["id"], dict(subject=var["name"], up="up", down="down", yes_if_up=None, relative=False, caveat=0))
    code = a["verdict"]["code"]
    slope = a["result"]["slope"] if a["result"]["slope"] is not None else 0.0
    bbox_selected = trend_map is None and a.get("bbox_selected", False)
    where = place_text(region_name, bbox_selected)
    units_short = var["trend_units"].split(" per ")[0]
    lines = [_main_sentence(ph, code, a, where, var["trend_units"])]
    if code != "insufficient_data":
        for extra in (_size_sentence(ph, a, units_short) if code != "ci_includes_zero" else None,
                      _where_sentence(ph, trend_map, a, bbox_selected, var["trend_units"]),
                      _confidence_sentence(a)):
            if extra:
                lines.append(extra)
        if a["verdict"].get("short_record"):
            lines.append(SHORT_RECORD)
    cc_line = cross_check_line(a.get("cross_check"))
    if cc_line:
        lines.append(cc_line)
    if compare and compare_var and compare.get("result", {}).get("slope") is not None:
        cr = compare["result"]
        same_dir = np.sign(cr["slope"]) == np.sign(slope)
        both_sig = _significant(compare) and _significant(a)
        verdict = ("They agree: same direction, both significant." if same_dir and both_sig else
                   "Same direction, but not both significant." if same_dir else
                   "They disagree on the direction – treat the result with care.")
        agree_head = "Yes – they agree." if same_dir and both_sig else "Partly." if same_dir else "No – they disagree."
        lines.insert(0, f"{ph.get('compare_label', 'the other dataset')[0].upper()}{ph.get('compare_label', 'the other dataset')[1:]} shows {num(cr['slope'])} "
                        f"{var['trend_units']} for the same area and {compare['start']}–{compare['end']}. {verdict}")
    caveat = None
    if var.get("caveats"):
        caveat = var["caveats"][min(ph.get("caveat", 0), len(var["caveats"]) - 1)]
    headline = _headline(ph, code, slope, a["verdict"].get("robustness"))
    if compare and compare_var and compare.get("result", {}).get("slope") is not None:
        headline = agree_head
    return dict(question=var["question"], headline=headline,
                code=code, lines=lines, caveat=caveat, how=_how(a),
                note="Built from the numbers on this page by fixed rules; no AI text generation.")
