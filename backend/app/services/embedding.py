"""
Embedding service with pluggable backends.

Backends (EMBEDDING_BACKEND):
  - auto:  local when sentence-transformers is importable, otherwise api.
           Source checkouts that installed the optional package keep using the
           free local model, while the packaged desktop sidecar — which cannot
           gain new packages after the build — falls back to the API endpoint.
  - local: sentence-transformers (gte-small, 384d).  The package is an optional
           extra and is not installed by backend/requirements.txt.
  - api:   OpenAI-compatible API (e.g., OpenAI, DeepSeek)

Configure via .env: EMBEDDING_BACKEND=auto|local|api
"""
import asyncio
import json
import logging
import os
import re
from importlib.util import find_spec
from typing import List, Optional
from urllib.parse import urlsplit, urlunsplit

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

LOCAL_MODEL_NAME = "TaylorAI/gte-small"
DEFAULT_API_MODEL = "text-embedding-3-small"


# ── Backend Resolution ──

def resolve_backend() -> str:
    """Resolve the effective backend, always to exactly "local" or "api".

    Read on every call rather than captured at import time, so a settings
    reload does not require restarting the process.  Never returns the raw
    setting: the runtime settings API accepts any string for
    EMBEDDING_BACKEND, and letting an unrecognised value through made callers
    disagree about what it meant.
    """
    backend = str(getattr(settings, "embedding_backend", "auto") or "auto").strip().lower()
    if backend in {"local", "api"}:
        return backend
    if backend != "auto":
        logger.warning(
            "Unknown EMBEDDING_BACKEND %r; falling back to auto detection.", backend
        )
    return "local" if find_spec("sentence_transformers") is not None else "api"


# ── Local Backend (sentence-transformers) ──

_model = None

def _get_local_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise RuntimeError(
                "EMBEDDING_BACKEND=local needs the optional 'sentence-transformers' "
                "package, which backend/requirements.txt does not install. Install it "
                "to use local embeddings, or set EMBEDDING_BACKEND=api to use an "
                "OpenAI-compatible embedding endpoint."
            ) from error
        _model = SentenceTransformer(LOCAL_MODEL_NAME)
    return _model


# ── API Backend (OpenAI-compatible) ──

_api_client = None

def _api_base_url() -> str:
    return str(settings.embedding_base_url or settings.llm_base_url or "").strip()


def _is_openai_endpoint(base_url: str) -> bool:
    host = urlsplit(base_url).hostname or ""
    return host == "api.openai.com" or host.endswith(".api.openai.com")


_URL_USERINFO = re.compile(r"//[^/@\s\"']*:[^/@\s\"']*@")


def redact_credentials(text: str) -> str:
    """Strip userinfo from every URL in arbitrary text.

    Provider errors embed the request URL in shapes we do not control, so
    substituting one known base URL string is not enough to keep a
    https://user:pass@host credential out of logs and API responses.
    """
    return _URL_USERINFO.sub("//", str(text))


def redacted_endpoint(base_url: str) -> str:
    """Endpoint without userinfo, safe to place in logs and error messages."""
    parts = urlsplit(base_url)
    if not parts.netloc:
        return base_url
    location = parts.hostname or ""
    if parts.port:
        location = f"{location}:{parts.port}"
    return urlunsplit((parts.scheme, location, parts.path, "", ""))


def resolve_api_model() -> str:
    """Resolve the embedding model name for the configured endpoint.

    A model name is meaningful only to the endpoint that serves it, so there is
    no portable default.  OpenAI's own endpoint gets one because it is the
    base_url shipped in .env.example; every other endpoint must say which model
    it serves rather than receive an OpenAI name it will reject.
    """
    configured = str(getattr(settings, "embedding_model", "") or "").strip()
    if configured:
        return configured
    base_url = _api_base_url()
    if _is_openai_endpoint(base_url):
        return DEFAULT_API_MODEL
    raise RuntimeError(
        "EMBEDDING_MODEL is not set and no default applies to "
        f"{redacted_endpoint(base_url) or 'the configured endpoint'}. Embeddings "
        "are a separate capability from chat: the provider behind LLM_BASE_URL "
        "may not serve them at all. Set EMBEDDING_MODEL (and EMBEDDING_BASE_URL "
        "when the embedding endpoint differs from the chat one), or install "
        "sentence-transformers to embed locally."
    )


def _get_api_client():
    global _api_client
    if _api_client is None:
        from openai import AsyncOpenAI
        # Use embedding-specific settings if provided, fallback to LLM settings
        api_key = settings.embedding_api_key or settings.llm_api_key
        base_url = _api_base_url()
        if not api_key:
            raise RuntimeError(
                "EMBEDDING_BACKEND=api needs EMBEDDING_API_KEY, or LLM_API_KEY to "
                "fall back on. Set one, or install sentence-transformers to embed "
                "locally."
            )
        _api_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    return _api_client


# ── Unified Interface ──

async def embed_text(text: str) -> List[float]:
    """Embed a single text. Returns a vector (384d local, model-defined via API)."""
    return (await embed_batch([text]))[0]


async def embed_batch(texts: List[str]) -> List[List[float]]:
    """Embed multiple texts in one round trip.

    Awaitable because both call sites are async: driving the OpenAI client with
    ``loop.run_until_complete`` from inside a running event loop raises
    ``RuntimeError: This event loop is already running``.
    """
    if resolve_backend() == "api":
        client = _get_api_client()
        response = await client.embeddings.create(model=resolve_api_model(), input=texts)
        ordered = sorted(response.data, key=lambda item: item.index)
        return [item.embedding for item in ordered]

    model = _get_local_model()
    # encode() is CPU-bound; keep it off the event loop.
    vectors = await asyncio.to_thread(
        model.encode, texts, normalize_embeddings=True, show_progress_bar=False
    )
    return [vector.tolist() for vector in vectors]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity (assumes L2-normalized vectors for dot product).

    Backends emit different dimensions, so a stale entry must score zero rather
    than raise and abort the whole retrieval pass.
    """
    if len(a) != len(b):
        return 0.0
    return float(np.dot(a, b))


# ── Disk Cache ──

DEFAULT_CACHE_DIR = "data/embeddings"


def cache_dir() -> str:
    """Writable directory holding the chunk embedding cache.

    Resolved per call rather than from ``__file__`` at import time.  A frozen
    PyInstaller onefile bundle extracts beside the module into a temporary
    directory that is deleted when the process exits, so the desktop sidecar
    points EMBEDDING_CACHE_DIR at the per-user application data directory the
    same way it already redirects the database and source caches.
    """
    return str(getattr(settings, "embedding_cache_dir", "") or DEFAULT_CACHE_DIR)


def cache_file() -> str:
    return os.path.join(cache_dir(), "chunk_embeddings.json")


def _cache_identity() -> dict:
    """Identify which backend and model produced the cached vectors.

    Never raises: reading the cache must stay possible while the api model is
    still unconfigured, otherwise a missing EMBEDDING_MODEL would break the
    keyword-only retrieval path too.
    """
    backend = resolve_backend()
    if backend == "local":
        return {"backend": backend, "model": LOCAL_MODEL_NAME}
    try:
        model = resolve_api_model()
    except RuntimeError:
        model = ""
    return {"backend": backend, "model": model}


def _read_cache_file() -> dict:
    path = cache_file()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, ValueError) as error:
        logger.warning("Embedding cache %s is unreadable (%s); treating as empty.", path, error)
        return {}
    return payload if isinstance(payload, dict) else {}


def load_cache() -> dict:
    """Return cached vectors, ignoring any written by a different backend/model."""
    payload = _read_cache_file()
    if not payload:
        return {}
    if "vectors" not in payload:
        logger.info("Ignoring embedding cache %s written before backend tagging.", cache_file())
        return {}
    if payload.get("identity") != _cache_identity():
        logger.info(
            "Ignoring embedding cache %s produced by %s; current backend is %s.",
            cache_file(), payload.get("identity"), _cache_identity(),
        )
        return {}
    vectors = payload.get("vectors")
    return vectors if isinstance(vectors, dict) else {}


def save_cache(cache: dict):
    """Replace the cache atomically.

    A plain truncating write leaves a partial file if the process dies or a
    reader arrives mid-write, and this file is shared by every request.
    """
    directory = cache_dir()
    os.makedirs(directory, exist_ok=True)
    target = cache_file()
    temporary = f"{target}.{os.getpid()}.tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump({"identity": _cache_identity(), "vectors": cache}, f)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def get_cached_embedding(chunk_id: int) -> Optional[List[float]]:
    cache = load_cache()
    return cache.get(f"chunk-{chunk_id}")


def cache_embedding(chunk_id: int, embedding: List[float]):
    cache_embeddings({chunk_id: embedding})


def cache_embeddings(embeddings: dict) -> int:
    """Persist several chunk vectors in one read/write cycle.

    Writing per chunk re-read and rewrote the whole file for every vector, so
    indexing a project cost O(n^2) bytes of disk traffic and widened the window
    for concurrent indexers to lose each other's updates.
    """
    if not embeddings:
        return 0
    cache = load_cache()
    for chunk_id, vector in embeddings.items():
        cache[f"chunk-{chunk_id}"] = vector
    save_cache(cache)
    return len(embeddings)
