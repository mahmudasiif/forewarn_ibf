"""Gemini REST client with a key pool — ported from the handover's
src/lib/gemini/{client,keyPool}.ts. Direct calls to the Generative Language API
(structured JSON generation + embeddings), with round-robin key failover on
429/503 so a pool of keys survives rate limits.
"""
from __future__ import annotations

import itertools
import os
import time

import httpx

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_GENERATION_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 3072


def _parse_keys() -> list[str]:
    multi = os.getenv("GOOGLE_API_KEYS", "")
    if multi.strip():
        return [k.strip() for k in multi.split(",") if k.strip()]
    single = os.getenv("GEMINI_API_KEY", "")
    return [single.strip()] if single.strip() else []


_KEYS = _parse_keys()
_cursor = itertools.count()


def key_count() -> int:
    # Re-read env each call so keys added after import are picked up.
    return len(_parse_keys())


def next_key() -> str:
    keys = _parse_keys()
    if not keys:
        raise RuntimeError(
            "No Gemini API key configured. Set GOOGLE_API_KEYS (comma-separated) "
            "or GEMINI_API_KEY."
        )
    return keys[next(_cursor) % len(keys)]


def _max_attempts() -> int:
    return max(1, min(key_count(), 12))


class GeminiError(RuntimeError):
    pass


def generate_content(
    prompt: str,
    *,
    system_instruction: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    max_output_tokens: int = 4096,
    response_schema: dict | None = None,
    timeout_s: float = 60.0,
    deadline: float | None = None,
) -> dict:
    """Call generateContent, trying each key in the pool on 429/503."""
    model = model or DEFAULT_GENERATION_MODEL

    generation_config: dict = {"maxOutputTokens": max_output_tokens}
    if temperature is not None:
        generation_config["temperature"] = temperature
    if top_p is not None:
        generation_config["topP"] = top_p
    if response_schema:
        generation_config["responseMimeType"] = "application/json"
        generation_config["responseSchema"] = response_schema

    body: dict = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }
    if system_instruction:
        body["systemInstruction"] = {"role": "system", "parts": [{"text": system_instruction}]}

    attempts = _max_attempts()
    last_error: Exception | None = None

    for attempt in range(attempts):
        if deadline is not None and time.time() >= deadline:
            raise last_error or GeminiError("Gemini generateContent deadline exceeded")
        api_key = next_key()
        url = f"{GEMINI_ENDPOINT}/{model}:generateContent?key={api_key}"
        try:
            resp = httpx.post(url, json=body, timeout=timeout_s)
        except httpx.HTTPError as exc:
            last_error = exc
            continue
        if resp.status_code in (429, 503):
            last_error = GeminiError(f"Gemini busy ({resp.status_code}) key {attempt + 1}/{attempts}")
            continue
        if resp.status_code != 200:
            raise GeminiError(f"Gemini API error: {resp.status_code} — {resp.text}")
        return resp.json()

    raise last_error or GeminiError("Gemini generateContent failed after exhausting key pool")


def extract_text(payload: dict) -> str:
    segments: list[str] = []
    for candidate in payload.get("candidates", []) or []:
        for part in (candidate.get("content", {}) or {}).get("parts", []) or []:
            text = (part.get("text") or "").strip()
            if text:
                segments.append(text)
    return "\n\n".join(segments).strip()


def embed_text(text: str) -> list[float]:
    attempts = _max_attempts()
    payload = {"model": f"models/{EMBEDDING_MODEL}", "content": {"parts": [{"text": text}]}}
    for _ in range(attempts):
        api_key = next_key()
        url = f"{GEMINI_ENDPOINT}/{EMBEDDING_MODEL}:embedContent?key={api_key}"
        resp = httpx.post(url, json=payload, timeout=60.0)
        if resp.status_code == 429:
            continue
        if resp.status_code != 200:
            raise GeminiError(f"Embedding API error: {resp.status_code} — {resp.text}")
        values = (resp.json().get("embedding", {}) or {}).get("values")
        if not values:
            raise GeminiError("Embedding returned no values")
        return values
    time.sleep(5)
    api_key = next_key()
    url = f"{GEMINI_ENDPOINT}/{EMBEDDING_MODEL}:embedContent?key={api_key}"
    resp = httpx.post(url, json=payload, timeout=60.0)
    if resp.status_code != 200:
        raise GeminiError(f"Embedding failed after key pool: {resp.status_code}")
    values = (resp.json().get("embedding", {}) or {}).get("values")
    if not values:
        raise GeminiError("Embedding failed: empty vector after retry")
    return values


def embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    out: list[list[float]] = []
    batch_size = 50
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        done = False
        for _ in range(_max_attempts()):
            api_key = next_key()
            url = f"{GEMINI_ENDPOINT}/{EMBEDDING_MODEL}:batchEmbedContents?key={api_key}"
            body = {
                "requests": [
                    {"model": f"models/{EMBEDDING_MODEL}", "content": {"parts": [{"text": t}]}}
                    for t in batch
                ]
            }
            try:
                resp = httpx.post(url, json=body, timeout=120.0)
            except httpx.HTTPError:
                continue
            if resp.status_code == 429:
                continue
            if resp.status_code != 200:
                break
            embeddings = resp.json().get("embeddings")
            if not embeddings or len(embeddings) != len(batch):
                break
            for emb in embeddings:
                vals = emb.get("values")
                if not vals:
                    raise GeminiError("Empty embedding in batch result")
                out.append(vals)
            done = True
            break
        if not done:
            for t in batch:
                out.append(embed_text(t))
    return out
