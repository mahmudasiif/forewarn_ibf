"""RAG grounding — ported from src/lib/rag/*.

Parses Neap_RAG.docx (python-docx), chunks it by heading, embeds the chunks into
an in-memory cosine vector store (numpy — no faiss), and retrieves NEAP policy +
optional Tavily web context for a given area/hazard query. The handover's
area-profile layer ships empty, so only the NEAP doc + web search are active.
Degrades to web-only / inactive when embeddings are unavailable (no key).
"""
from __future__ import annotations

import os

import httpx
import numpy as np
from docx import Document

from app.guidance import gemini
from app.settings import settings

NEAP_DOC = os.path.join(settings.ASSETS_DIR, "Neap_RAG.docx")

MAX_CHUNK_CHARS = 1600
OVERLAP_CHARS = 200
MIN_CHUNK_CHARS = 80
NEAP_TOP_K = 4
WEB_SEARCH_TOP_K = 4

_TAVILY_ENDPOINT = "https://api.tavily.com/search"


# ------------------------------------------------------------------ docx parse
def parse_docx(path: str) -> str:
    doc = Document(path)
    lines: list[str] = []
    for p in doc.paragraphs:
        text = p.text or ""
        style = (p.style.name if p.style else "") or ""
        if style.lower().startswith("heading") and text.strip():
            lines.append(f"## {text.strip()}")
        else:
            lines.append(text)
    return "\n".join(lines).strip()


# ------------------------------------------------------------------ chunker
import re  # noqa: E402

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$")
_BOLD_HEADING_RE = re.compile(r"^__(.+)__$")


def _extract_heading(line: str) -> str | None:
    t = line.strip()
    if not t:
        return None
    m = _HEADING_RE.match(t)
    if m:
        return m.group(2).strip()
    m = _BOLD_HEADING_RE.match(t)
    if m and len(m.group(1)) < 200:
        cleaned = (
            m.group(1)
            .replace("\\*\\*", "")
            .replace("**", "")
            .replace("\\(", "(")
            .replace("\\)", ")")
            .replace("\\", "")
            .strip()
        )
        if cleaned:
            return cleaned
    return None


def _split_into_sections(text: str) -> list[dict]:
    sections: list[dict] = []
    current_heading = "Introduction"
    current_body: list[str] = []
    for line in text.split("\n"):
        heading = _extract_heading(line)
        if heading:
            if current_body or not sections:
                body = "\n".join(current_body).strip()
                if body:
                    sections.append({"heading": current_heading, "body": body})
            current_heading = heading
            current_body = []
        else:
            current_body.append(line)
    if current_body:
        body = "\n".join(current_body).strip()
        if body:
            sections.append({"heading": current_heading, "body": body})
    return [s for s in sections if len(s["body"]) >= MIN_CHUNK_CHARS]


def _sub_split(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    paragraphs = re.split(r"\n\n+", text)
    if len(paragraphs) <= 1:
        paragraphs = text.split("\n")
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) > max_chars and len(current) >= MIN_CHUNK_CHARS:
            chunks.append(current.strip())
            overlap_text = current[-overlap:]
            current = f"{overlap_text}\n\n{para}" if overlap_text else para
        else:
            current = candidate
    tail = current.strip()
    if len(tail) >= MIN_CHUNK_CHARS:
        chunks.append(tail)
    elif tail and chunks:
        chunks[-1] += "\n\n" + tail
    elif tail:
        chunks.append(tail)
    return chunks


def chunk_document(text: str, source: str = "neap", district: str | None = None) -> list[dict]:
    chunks: list[dict] = []
    idx = 0
    for section in _split_into_sections(text):
        for sub in _sub_split(section["body"], MAX_CHUNK_CHARS, OVERLAP_CHARS):
            chunks.append(
                {
                    "text": sub,
                    "metadata": {
                        "source": source,
                        "district": district,
                        "section": section["heading"],
                        "chunkIndex": idx,
                    },
                }
            )
            idx += 1
    return chunks


# ------------------------------------------------------------------ vector store
class VectorStore:
    def __init__(self) -> None:
        self._chunks: list[dict] = []
        self._matrix: np.ndarray | None = None

    def add(self, chunks: list[dict], embeddings: list[list[float]]) -> None:
        self._chunks = list(chunks)
        self._matrix = np.array(embeddings, dtype=np.float32) if embeddings else None

    def size(self) -> int:
        return len(self._chunks)

    def search(self, query_vec: list[float], source: str | None = None, top_k: int = 5) -> list[dict]:
        if self._matrix is None or not self._chunks:
            return []
        idxs = [i for i, c in enumerate(self._chunks) if not source or c["metadata"]["source"] == source]
        if not idxs:
            return []
        q = np.array(query_vec, dtype=np.float32)
        qn = np.linalg.norm(q)
        sub = self._matrix[idxs]
        denom = (np.linalg.norm(sub, axis=1) * qn)
        denom[denom == 0] = 1e-9
        scores = sub @ q / denom
        order = np.argsort(-scores)[:top_k]
        return [{"chunk": self._chunks[idxs[o]], "score": float(scores[o])} for o in order]


_store: VectorStore | None = None


def _init_store() -> VectorStore:
    global _store
    if _store is not None:
        return _store
    vs = VectorStore()
    try:
        text = parse_docx(NEAP_DOC)
        chunks = chunk_document(text, "neap")
        if chunks:
            embeddings = gemini.embed_batch([c["text"] for c in chunks])
            vs.add(chunks, embeddings)
            print(f"[RAG] embedded {vs.size()} NEAP chunks", flush=True)
    except Exception as exc:  # noqa: BLE001 - RAG is optional grounding
        print(f"[RAG] init failed ({exc}); continuing web-only/inactive", flush=True)
    _store = vs
    return vs


def is_ready() -> bool:
    return _store is not None and _store.size() > 0


# ------------------------------------------------------------------ web search
def search_web(query: str, max_results: int = 5) -> list[dict]:
    key = os.getenv("TAVILY_API_KEY", "")
    if not key.strip():
        return []
    try:
        resp = httpx.post(
            _TAVILY_ENDPOINT,
            json={
                "api_key": key,
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
                "include_answer": False,
            },
            timeout=8.0,
        )
        if resp.status_code != 200:
            return []
        results = resp.json().get("results", []) or []
        return [
            {"title": r["title"], "url": r["url"], "content": (r.get("content") or "")[:800]}
            for r in results
            if r.get("title") and r.get("url") and r.get("content")
        ]
    except Exception:  # noqa: BLE001
        return []


# ------------------------------------------------------------------ retrieve
def _build_web_query(params: dict) -> str:
    place = ", ".join(p for p in (params.get("upazila"), params.get("district")) if p)
    return f"{place} Bangladesh cyclone flood storm surge risk coastal preparedness".strip()


def _build_retrieval_query(params: dict) -> str:
    parts: list[str] = []
    if params.get("district"):
        parts.append(params["district"])
    if params.get("upazila"):
        parts.append(params["upazila"])
    if params.get("windSpeed") is not None:
        parts.append(f"বাতাসের গতি {params['windSpeed']} কিমি/ঘণ্টা wind speed {params['windSpeed']} km/h")
    if params.get("windClass"):
        parts.append(f"বাতাসের শ্রেণী {params['windClass']}")
    if params.get("rainfall") is not None:
        parts.append(f"বৃষ্টিপাত {params['rainfall']} মিমি rainfall {params['rainfall']} mm")
    if params.get("stormSurge") is not None:
        parts.append(f"ঝড়জলোচ্ছ্বাস {params['stormSurge']} মিটার storm surge {params['stormSurge']} m")
    if params.get("risk"):
        parts.append(f"ঝুঁকি {params['risk']} risk")
    parts.append("ক্ষয়ক্ষতি সরিয়ে নেওয়া আশ্রয় প্রস্তুতি damage evacuation shelter preparedness")
    return " ".join(parts)


def _build_references(chunk_results: list[dict], web_results: list[dict]) -> list[dict]:
    refs: list[dict] = []
    n = 1
    for r in chunk_results:
        chunk = r["chunk"]
        section = chunk["metadata"].get("section") or "সাধারণ"
        refs.append(
            {"n": n, "type": "neap", "title": f"NEAP নীতিমালা — {section}", "snippet": chunk["text"][:600]}
        )
        n += 1
    for w in web_results:
        refs.append({"n": n, "type": "web", "title": w["title"], "url": w["url"], "snippet": w["content"][:600]})
        n += 1
    return refs


def _format_references(refs: list[dict]) -> str:
    if not refs:
        return ""
    lines: list[str] = []
    for ref in refs:
        icon = "🌐" if ref["type"] == "web" else "📋"
        source = f" ({ref['url']})" if ref.get("url") else ""
        lines.append(f"**[তথ্যসূত্র {ref['n']}]** {icon} {ref['title']}{source}")
        if ref.get("snippet"):
            lines.append(ref["snippet"])
        lines.append("---")
    return "\n".join(lines)


def retrieve(params: dict) -> dict:
    """Return NEAP + web grounding context for one area/hazard query."""
    store = _init_store()
    web_query = _build_web_query(params)
    web_results = search_web(web_query, WEB_SEARCH_TOP_K)

    results: list[dict] = []
    if store.size() > 0:
        try:
            qvec = gemini.embed_text(_build_retrieval_query(params))
            results = store.search(qvec, source="neap", top_k=NEAP_TOP_K)
        except Exception as exc:  # noqa: BLE001
            print(f"[RAG] query embedding failed ({exc})", flush=True)

    references = _build_references(results, web_results)
    return {
        "results": results,
        "webResults": web_results,
        "references": references,
        "formattedContext": _format_references(references),
    }
