"""Load model weights once at process start and hold them in memory."""
from pathlib import Path

from app.settings import settings

_model = None


def load_model():
    """TODO: load the actual artefact from settings.WEIGHTS_DIR."""
    global _model
    if _model is None:
        weights = Path(settings.WEIGHTS_DIR)
        _model = {"loaded_from": str(weights), "ready": weights.exists()}
    return _model


def is_ready() -> bool:
    return load_model() is not None
