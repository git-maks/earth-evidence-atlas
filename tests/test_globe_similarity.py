from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(not shutil.which("node"), reason="Node is needed to exercise the browser search")
def test_similarity_uses_weighted_trends_and_excludes_overlapping_or_missing_windows():
    script = """
const assert = require("assert"), fs = require("fs"), vm = require("vm");
vm.runInThisContext(fs.readFileSync(process.argv[1], "utf-8"));
const grid = {
  lat: [-60, 0, 60], lon: [-5, -3, -1, 1, 3, 5],
  slope: [[3, 3, 3, 3, -3, -3], [0, 0, 0, 0, 0, 0], [null, null, null, null, -1, -1]],
};
const search = findSimilarWindows(grid, [-6, -90, -2, 29], 0.01, 5);
assert(Math.abs(search.reference - 1) < 1e-10);
assert.strictEqual(search.cells, 4);
assert.strictEqual(search.matches.length, 1);
assert.deepStrictEqual(search.matches[0].bbox, [-2, -90, 2, 30]);
assert(search.matches[0].difference < 1e-10);
assert.strictEqual(findSimilarWindows(grid, [-5, 59, -4, 61], 1, 5), null);
const singleCell = findSimilarWindows(grid, [-5.1, -59.8, -4.9, -59.6], 10, 2);
assert.strictEqual(singleCell.cells, 1);
assert.strictEqual(singleCell.matches.length, 2);
assert(singleCell.matches.every(({ trend }) => trend >= 0));
"""
    module = Path(__file__).resolve().parents[1] / "web" / "globe-similarity.js"
    run = subprocess.run(["node", "-e", script, str(module)], capture_output=True, text=True, timeout=10)
    assert run.returncode == 0, run.stderr
