"""Answers are fixed templates filled from the analysis numbers (AI disclosure: tests written with Claude)."""
from atlas import answers
from atlas.config import VARIABLES


def _a(slope, code, lo=None, hi=None, months=None, rob=None):
    dates = [f"{y}-{m:02d}" for y in range(2001, 2025) for m in range(1, 13)]
    an = [((i % 12) - 5.5) * 0.01 + slope / 120 * i for i in range(len(dates))]
    return dict(variable="t2m", start=2001, end=2024, months=months or list(range(1, 13)), cells=12,
                bbox_selected=False, trend_units="°C per decade",
                result=dict(slope=slope, ci_low=lo if lo is not None else slope - 0.1, ci_high=hi if hi is not None else slope + 0.1,
                            p=0.001, n=288, n_eff=90, r1=0.5, mk_p=0.001, mk_z=3, sen_slope=slope, valid_fraction=1.0),
                verdict=dict(code=code, robustness=rob or dict(windows=55, same_sign=55, same_sign_significant=50)),
                series=dict(dates=dates, anomaly=an, absolute=[10 + x for x in an]))


def test_yes_no_and_direction():
    v = VARIABLES["t2m"].public()
    up = answers.build(v, "Central Europe (Poland)", _a(0.5, "trend_detected"))
    down = answers.build(v, "Central Europe (Poland)", _a(-0.5, "trend_detected"))
    assert up["headline"] == "Yes – warmer." and down["headline"] == "No – cooler."
    assert "+0.5 °C per decade" in up["lines"][0] and "Central Europe" in up["lines"][0]
    assert "no AI" in up["note"]


def test_uncertain_and_period_dependent_never_claim_a_trend():
    v = VARIABLES["t2m"].public()
    unsure = answers.build(v, "X", _a(0.05, "ci_includes_zero", lo=-0.1, hi=0.2))
    assert unsure["headline"] == "We can't tell yet." and "includes zero" in unsure["lines"][0]
    dep = answers.build(v, "X", _a(0.3, "depends_on_period", rob=dict(windows=40, same_sign=20, same_sign_significant=5)))
    assert dep["headline"] == "It depends on the period." and "20 of 40" in dep["lines"][0]
    none = answers.build(v, "X", _a(0.3, "insufficient_data"))
    assert none["headline"] == "Not enough data to say." and len(none["lines"]) == 1


def test_season_and_relative_change():
    v = VARIABLES["precip"].public()
    a = _a(0.2, "trend_detected", months=[6, 7, 8])
    out = answers.build(v, "X", a)
    assert out["headline"] == "More." and "summer (Jun–Aug)" in out["lines"][0]
    assert "% of the usual level" in " ".join(out["lines"])
