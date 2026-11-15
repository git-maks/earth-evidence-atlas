"""Runs the browser-free tour engine checks in tests/test_tour.js with Node."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not shutil.which("node"), reason="Node is needed to exercise the tour engine")
def test_tour_engine_syntax_and_logic():
    check = subprocess.run(["node", "--check", str(ROOT / "web/tour.js")], text=True, capture_output=True, cwd=ROOT, timeout=30)
    assert check.returncode == 0, check.stderr
    process = subprocess.run(["node", str(ROOT / "tests/test_tour.js")], text=True, capture_output=True, cwd=ROOT, timeout=60)
    assert process.returncode == 0, process.stdout + process.stderr
