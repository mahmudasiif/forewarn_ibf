"""Reference-data loading for the CCM engine.

The union boundaries and the polder/structure/housing tables are the same for
every run, and reading them costs a few seconds (the agricultural-land layer
alone is ~50 MB), so they are loaded once on startup and reused.
"""
from __future__ import annotations

from app.model.engine import CCMReferenceData, load_reference_data
from app.settings import settings

_reference: CCMReferenceData | None = None
_error: str | None = None


def load() -> CCMReferenceData:
    """Loads (once) and returns the reference data every run needs."""
    global _reference, _error
    if _reference is None:
        try:
            _reference = load_reference_data(settings.CCM_DATA_DIR)
            _error = None
        except Exception as exc:  # noqa: BLE001 — surfaced through /info and /runs
            _error = f"{type(exc).__name__}: {exc}"
            raise
    return _reference


def is_ready() -> bool:
    """True when the reference data is loaded and runs can be served."""
    return _reference is not None


def last_error() -> str | None:
    return _error
