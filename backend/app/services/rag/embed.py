"""Sentence embeddings for vector search (sentence-transformers on PyTorch, runs on the laptop's CPU).

Optional: without the package (or with ENABLE_EMBEDDINGS=false) the library still works and search uses
Postgres keyword search instead. The model is loaded once, on first use, and downloaded the very first time.
"""

import logging
import threading
from typing import Optional

from app.core.config import settings

log = logging.getLogger("raazicid.embed")
_lock = threading.Lock()
_model = None
_error: Optional[str] = None


def _load():
    global _model, _error
    if _model is not None or _error is not None:
        return _model
    with _lock:
        if _model is not None or _error is not None:
            return _model
        if not settings.ENABLE_EMBEDDINGS:
            _error = "Turned off (ENABLE_EMBEDDINGS=false)"
            return None
        try:
            from sentence_transformers import SentenceTransformer
        except Exception:  # not installed, or torch missing
            _error = "Not installed: pip install sentence-transformers"
            return None
        try:
            m = SentenceTransformer(settings.EMBEDDING_MODEL, device="cpu")
            dim = m.get_sentence_embedding_dimension()
            if dim != settings.EMBEDDING_DIM:
                _error = f"Model gives {dim} numbers, the database expects {settings.EMBEDDING_DIM}"
                return None
            _model = m
            log.info("embedding model ready: %s", settings.EMBEDDING_MODEL)
        except Exception as e:  # no internet for the first download, etc.
            _error = f"Could not load the model: {e}"[:300]
            log.warning(_error)
    return _model


def status() -> dict:
    """For the admin page. Does not load the model."""
    if _model is not None:
        return {"available": True, "model": settings.EMBEDDING_MODEL, "note": "Vector search on"}
    if _error is not None:
        return {"available": False, "model": settings.EMBEDDING_MODEL, "note": _error}
    if not settings.ENABLE_EMBEDDINGS:
        return {"available": False, "model": settings.EMBEDDING_MODEL, "note": "Turned off (ENABLE_EMBEDDINGS=false)"}
    try:
        import importlib.util
        installed = importlib.util.find_spec("sentence_transformers") is not None
    except Exception:
        installed = False
    return {"available": installed, "model": settings.EMBEDDING_MODEL,
            "note": "Loads on first use" if installed else "Not installed: pip install sentence-transformers"}


def embed(texts: list[str]) -> Optional[list[list[float]]]:
    """Unit-length vectors (cosine distance works directly), or None when embeddings are not available."""
    if not texts:
        return []
    model = _load()
    if model is None:
        return None
    vecs = model.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vecs]
