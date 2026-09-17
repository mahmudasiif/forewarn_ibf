#!/usr/bin/env bash
# Copy the Preparedness Guidance model's static assets (GIS boundaries, housing
# CSV, structure-damage workbook, NEAP sources) out of the hackathon handover
# into services/preparedness/assets/, which is git-ignored (~206 MB).
#
# Override the handover location with HANDOVER_DIR=... if it lives elsewhere.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/services/preparedness/assets"
HANDOVER_DIR="${HANDOVER_DIR:-$ROOT/Cyclone-AI-Guideline-Handover/Cyclone-AI-Guideline-Handover/Files}"

if [ ! -d "$HANDOVER_DIR" ]; then
    echo "Handover Files/ not found at: $HANDOVER_DIR" >&2
    echo "Set HANDOVER_DIR=/path/to/Cyclone-AI-Guideline-Handover/.../Files and re-run." >&2
    exit 1
fi

mkdir -p "$DEST"
echo "Copying assets from $HANDOVER_DIR -> $DEST ..."

# Everything the pipeline reads at runtime. app.py / service.py / requirements.txt
# are the handover's own code and are intentionally excluded.
copy() {
    local item="$1"
    if [ -e "$HANDOVER_DIR/$item" ]; then
        cp -r "$HANDOVER_DIR/$item" "$DEST/"
        echo "  + $item"
    else
        echo "  ! missing (skipped): $item" >&2
    fi
}

copy "BD Union BBS 2022"
copy "BD Upazila BBS 2022"
copy "BD District BBS 2022"
copy "union_bbs.csv"
copy "StructureDamageData.xlsx"
copy "Neap_RAG.docx"
copy "NEAP sector-wise actions spreadsheet-selected"
# Legacy union shapefile (fallback in load_household_data)
for ext in shp dbf shx prj cpg; do
    copy "BD_Union_BBS21.$ext"
done

echo "Done. $(du -sh "$DEST" | cut -f1) in $DEST"
