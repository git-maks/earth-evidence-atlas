"""Build a curated static Pages artifact. No application checkout or live API is required."""
from __future__ import annotations

from pathlib import Path
import shutil

import build
from checks import PUBLIC_FILES, check_artifacts, check_snapshot

HERE = Path(__file__).resolve().parent


def main():
    check_snapshot()
    build.main()
    check_artifacts()
    output = HERE / "_site"
    # This folder is generated and ignored by Git; never copy archives or development scripts.
    if output.exists():
        shutil.rmtree(output)
    output.mkdir()
    for name in PUBLIC_FILES:
        shutil.copy2(HERE / name, output / name)
    check_artifacts(output)
    assert {path.name for path in output.iterdir()} == set(PUBLIC_FILES)
    print(f"Pages artifact ready: {output} ({len(PUBLIC_FILES)} files)")


if __name__ == "__main__":
    main()

