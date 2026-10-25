"""Donation photo classifier (Phase 5): MobileNetV2 trained in ml/train_classifier.ipynb, run with PyTorch.

PyTorch is optional. Without it, or without the model files, `status()` says why and the apps let the donor
choose the category themselves.
"""

import io
import json
import threading
from pathlib import Path
from typing import Any, Optional

from app.core.config import settings

MODEL_FILE = "raazicid_classifier.pt"
LABELS_FILE = "labels.json"


class Classifier:
    def __init__(self, folder: str):
        self.folder = Path(folder)
        self._lock = threading.Lock()
        self._model = None
        self._info: Optional[dict[str, Any]] = None
        self._error: Optional[str] = None
        self._tried = False

    def _load(self) -> None:
        if self._tried:
            return
        self._tried = True
        try:
            import torch  # noqa: F401
        except ImportError:
            self._error = "not_installed"   # pip install torch --index-url https://download.pytorch.org/whl/cpu
            return
        model_path, labels_path = self.folder / MODEL_FILE, self.folder / LABELS_FILE
        if not model_path.exists() or not labels_path.exists():
            self._error = "no_model"        # copy the two files from Google Drive into backend/models/
            return
        import torch

        torch.set_num_threads(2)
        self._info = json.loads(labels_path.read_text(encoding="utf-8"))
        self._model = torch.jit.load(str(model_path), map_location="cpu").eval()

    def status(self) -> dict[str, Any]:
        with self._lock:
            self._load()
        if self._model is None:
            return {"classifier": self._error or "no_model", "version": None, "accuracy": None, "own_photo_accuracy": None}
        m = self._info.get("metrics") or {}
        acc = lambda k: (m.get(k) or {}).get("accuracy")  # noqa: E731
        return {"classifier": "ready", "version": self._info.get("version"),
                "accuracy": acc("open_images_test"), "own_photo_accuracy": acc("own_photos")}

    @property
    def ready(self) -> bool:
        return self.status()["classifier"] == "ready"

    @property
    def version(self) -> Optional[str]:
        return self._info.get("version") if self._info else None

    def _tensor(self, image_bytes: bytes):
        """Same preprocessing as the notebook's eval transform: resize short side, centre crop, normalise."""
        import torch
        from PIL import Image

        size, resize = int(self._info["input_size"]), int(self._info.get("resize", 256))
        im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = im.size
        scale = resize / min(w, h)
        im = im.resize((max(size, round(w * scale)), max(size, round(h * scale))), Image.BILINEAR)
        w, h = im.size
        left, top = (w - size) // 2, (h - size) // 2
        im = im.crop((left, top, left + size, top + size))
        x = torch.frombuffer(bytearray(im.tobytes()), dtype=torch.uint8).view(size, size, 3).permute(2, 0, 1).float() / 255
        mean = torch.tensor(self._info["mean"]).view(3, 1, 1)
        std = torch.tensor(self._info["std"]).view(3, 1, 1)
        return ((x - mean) / std).unsqueeze(0)

    def predict(self, image_bytes: bytes, top: int = 3) -> list[dict[str, Any]]:
        """[{"category_id": 4, "p": 0.92, "shared": False}, ...] best first."""
        import torch

        with self._lock:
            self._load()
            if self._model is None:
                raise RuntimeError(self._error or "no_model")
            with torch.no_grad():
                probs = torch.softmax(self._model(self._tensor(image_bytes)), dim=1)[0].tolist()
        return expand(probs, self._info["categories"], top)


def expand(probs: list[float], categories: list[dict[str, Any]], top: int = 3) -> list[dict[str, Any]]:
    """Turn model outputs into category suggestions.

    A model class can stand for one category ({"category_id": 4}) or a group trained together
    ({"category_ids": [4, 5]}, e.g. blankets + winter support). A group's probability is given to each of its
    categories with "shared": True, so the app shows both and lets the donor pick.
    """
    out = []
    for c in categories:
        ids = c.get("category_ids") or [c["category_id"]]
        p = round(float(probs[c["index"]]), 4)
        out += [{"category_id": cid, "p": p, "shared": len(ids) > 1} for cid in ids]
    out.sort(key=lambda s: -s["p"])
    return out[:top]


classifier = Classifier(settings.CLASSIFIER_DIR)
