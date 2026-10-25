"""Sentence embeddings for vector search (sentence-transformers on PyTorch, runs on the laptop's CPU).

Optional: without the package (or with ENABLE_EMBEDDINGS=false) the library still works and search uses
Postgres keyword search instead. The model is loaded in the background when the backend starts (and downloaded
the very first time), so no request has to wait for it: searches use keywords only until it is ready.
"""

import importlib.util
import logging
import threading
from typing import Optional

from app.core.config import settings

log = logging.getLogger("raazicid.embed")
_lock = threading.Lock()
_model = None
_error: Optional[str] = None
_loading = False


def _installed() -> bool:
    try:
        return importlib.util.find_spec("sentence_transformers") is not None
    except Exception:
        return False


def _load(wait: bool = True):
    """The model, loading it if needed. With wait=False, returns None instead of waiting for a load in progress."""
    global _model, _error, _loading
    if _model is not None or _error is not None:
        return _model
    if not wait and _loading:
        return None
    with _lock:
        if _model is not None or _error is not None:
            return _model
        if not settings.ENABLE_EMBEDDINGS:
            _error = "Turned off (ENABLE_EMBEDDINGS=false)"
            return None
        if not _installed():
            _error = "Not installed: pip install sentence-transformers"
            return None
        _loading = True
        try:
            from sentence_transformers import SentenceTransformer

            m = SentenceTransformer(settings.EMBEDDING_MODEL, device="cpu")
            size = getattr(m, "get_embedding_dimension", None) or m.get_sentence_embedding_dimension
            dim = size()
            if dim != settings.EMBEDDING_DIM:
                _error = f"Model gives {dim} numbers, the database expects {settings.EMBEDDING_DIM}"
            else:
                _model = m
                log.info("embedding model ready: %s", settings.EMBEDDING_MODEL)
        except Exception as e:  # no internet for the first download, etc.
            _error = f"Could not load the model: {e}"[:300]
            log.warning(_error)
        finally:
            _loading = False
    return _model


def warm_up() -> None:
    """Load (and the first time download) the model in a background thread at startup."""
    if settings.ENABLE_EMBEDDINGS and _installed() and _model is None and _error is None:
        threading.Thread(target=_load, name="embedding-warm-up", daemon=True).start()


def status() -> dict:
    """For the admin page. Never loads the model."""
    if _model is not None:
        return {"available": True, "model": settings.EMBEDDING_MODEL, "note": "Vector search on"}
    if _error is not None:
        return {"available": False, "model": settings.EMBEDDING_MODEL, "note": _error}
    if not settings.ENABLE_EMBEDDINGS:
        return {"available": False, "model": settings.EMBEDDING_MODEL, "note": "Turned off (ENABLE_EMBEDDINGS=false)"}
    if _loading:
        return {"available": False, "model": settings.EMBEDDING_MODEL,
                "note": "Loading the model (the first time it downloads about 470 MB); keyword search until then"}
    installed = _installed()
    return {"available": installed, "model": settings.EMBEDDING_MODEL,
            "note": "Loads on first use" if installed else "Not installed: pip install sentence-transformers"}


def embed(texts: list[str], wait: bool = True) -> Optional[list[list[float]]]:
    """Unit-length vectors (cosine distance works directly), or None when embeddings are not available.
    wait=False (searches): do not wait while the model is still loading."""
    if not texts:
        return []
    model = _load(wait)
    if model is None:
        return None
    vecs = model.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vecs]
