#!/usr/bin/env python3
"""Prepare the DFRM model service's static assets (git-ignored, ~20 MB).

Copies the DFRM v5.2 reference database (shapefiles + spreadsheets) out of the
source drop into ``services/dfrm/assets/DFRM_Database/``. That directory is
git-ignored and mounted read-only into the container.

The map's admin context outlines (upazila / district) are derived at runtime by
dissolving the DFRM union geometry itself — no external boundary files needed.

Override the source location if it lives elsewhere:
    DFRM_SRC="/path/to/DFRM v5.2 - For Share" python3 scripts/dfrm_setup_assets.py

Re-runnable: existing files are overwritten.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "services" / "dfrm" / "assets" / "DFRM_Database"
DFRM_SRC = Path(os.environ.get("DFRM_SRC", ROOT / "DFRM" / "DFRM v5.2 - For Share"))


def copy_database() -> None:
    src_db = DFRM_SRC / "DFRM_Database"
    if not src_db.is_dir():
        print(f"  ! DFRM_Database not found at {src_db}", file=sys.stderr)
        print("    Set DFRM_SRC=/path/to/'DFRM v5.2 - For Share' and re-run.", file=sys.stderr)
        sys.exit(1)
    DEST.mkdir(parents=True, exist_ok=True)
    count = 0
    for item in src_db.iterdir():
        if item.is_file():
            shutil.copy2(item, DEST / item.name)
            count += 1
    print(f"  + copied {count} files -> {DEST}")


if __name__ == "__main__":
    print(f"DFRM assets -> {DEST}")
    copy_database()
    print("Done.")
