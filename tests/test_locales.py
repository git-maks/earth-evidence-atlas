"""Locale compatibility and regression checks for translated scientific answers."""
import json
import re
import shutil
import subprocess
from collections import Counter
from copy import deepcopy
from pathlib import Path
from html.parser import HTMLParser

import pytest

from atlas import answers
from atlas.config import VARIABLES

ROOT = Path(__file__).resolve().parents[1]


def leaves(value, path=""):
    if isinstance(value, (dict, list)):
        items = value.items() if isinstance(value, dict) else enumerate(value)
        return {p: v for key, child in items for p, v in leaves(child, f"{path}.{key}").items()}
    return {path: value}


def test_locale_keys_placeholders_and_markup_match():
    locales = {lang: leaves(json.loads((ROOT / f"web/locales/{lang}.json").read_text())) for lang in ("en", "es", "pl")}
    for lang, entries in locales.items():
        assert entries.keys() == locales["en"].keys(), lang
        for key, text in entries.items():
            assert isinstance(text, str) and text.strip(), (lang, key)
            english = locales["en"][key]
            assert Counter(re.findall(r"\{\w+\}", text)) == Counter(re.findall(r"\{\w+\}", english)), (lang, key)
            assert re.findall(r"</?b>|<br>", text) == re.findall(r"</?b>|<br>", english), (lang, key)


def test_static_translation_bindings_are_valid_html_and_existing_keys():
    resources = leaves(json.loads((ROOT / "web/locales/en.json").read_text()))

    class Bindings(HTMLParser):
        in_option = False

        def handle_starttag(self, tag, attrs):
            assert not self.in_option, "Options must contain text rather than nested translation elements"
            self.in_option = tag == "option"
            assert len({key for key, _ in attrs}) == len(attrs), (tag, attrs)
            for name, value in attrs:
                assert re.fullmatch(r"[a-zA-Z][a-zA-Z0-9:_-]*", name), (tag, name)
                if name in ("data-i18n", "data-i18n-html"):
                    assert "." + value in resources, value
                if name == "data-i18n-attrs":
                    for binding in value.split(";"):
                        attribute, key = binding.split(":")
                        assert attribute and "." + key in resources, binding

        def handle_endtag(self, tag):
            if tag == "option":
                self.in_option = False

    Bindings().feed((ROOT / "web/index.html").read_text())


@pytest.mark.skipif(not shutil.which("node"), reason="Node is needed to exercise the browser localisation module")
def test_runtime_preserves_values_and_translates_answer_variants():
    dates = [f"{year}-{month:02}" for year in range(2001, 2025) for month in range(1, 13)]
    fixtures = []
    for variable in VARIABLES.values():
        for code in ("trend_detected", "depends_on_period", "significance_depends_on_period",
                     "ci_includes_zero", "insufficient_data"):
            for slope in (0.5, -0.5):
                raw = dict(variable=variable.id, start=2001, end=2024, months=[6, 7, 8], cells=1,
                           bbox_selected=True, units=variable.units, trend_units=variable.trend_units,
                           result=dict(slope=slope, ci_low=slope-0.1, ci_high=slope+0.1, p=0.001,
                                       n=288, n_eff=90, mk_p=0.001, sen_slope=slope, valid_fraction=0.9,
                                       p_year=0.004, n_year=24),
                           verdict=dict(code=code, methods_agree=True, short_record=slope < 0,
                                        robustness=dict(same_sign=20, windows=40, same_sign_significant=12,
                                                        long_windows=21, long_significant=6)),
                           series=dict(dates=dates, anomaly=[i * slope / 120 for i in range(len(dates))],
                                       absolute=[10 + i * slope / 120 for i in range(len(dates))]))
                if code == "ci_includes_zero":
                    raw["result"].update(ci_low=-0.6, ci_high=0.6)
                comparison = deepcopy(raw) if variable.id == "lst_day_aqua" else None
                raw["answer"] = answers.build(variable.public(), "Central Europe (Poland)", raw,
                                              compare=comparison, compare_var=VARIABLES["lst_day"].public() if comparison else None)
                fixtures.append(raw)
    process = subprocess.run(["node", str(ROOT / "tests/test_i18n.js")], input=json.dumps(fixtures),
                             text=True, capture_output=True, cwd=ROOT, timeout=30)
    assert process.returncode == 0, process.stdout + process.stderr
