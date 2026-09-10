"""Turn raw model output into the documented response shape."""


def postprocess(raw) -> dict:
    return {"raw": raw}
