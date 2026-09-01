from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import ImageGrab

from core.project import APP_ROOT


SCREENSHOT_ROOT = APP_ROOT / "work" / "auto_pilot" / "screenshots"
_OCR_ENGINE: Any = None


def screen_capture(
    *,
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> dict[str, Any]:
    SCREENSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    bbox = None
    if any(value is not None for value in (x, y, width, height)):
        values = (x, y, width, height)
        if any(value is None for value in values):
            raise ValueError("Cần cung cấp đủ x, y, width và height.")
        if width <= 0 or height <= 0:
            raise ValueError("width và height phải lớn hơn 0.")
        bbox = (x, y, x + width, y + height)
    try:
        image = ImageGrab.grab(bbox=bbox, all_screens=True)
    except Exception:
        image = ImageGrab.grab(bbox=bbox)
    path = SCREENSHOT_ROOT / (
        datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".png"
    )
    image.save(path, format="PNG")
    return {
        "path": str(path),
        "width": image.width,
        "height": image.height,
        "region": bbox,
    }


def screen_ocr(
    *,
    image_path: str = "",
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
    min_confidence: float = 0.35,
) -> dict[str, Any]:
    if image_path.strip():
        path = Path(image_path).expanduser().resolve()
        if not path.is_relative_to(APP_ROOT.resolve()):
            raise ValueError("Ảnh OCR phải nằm trong workspace.")
        if not path.is_file():
            raise FileNotFoundError(f"Không tìm thấy ảnh: {path}")
    else:
        capture = screen_capture(
            x=x,
            y=y,
            width=width,
            height=height,
        )
        path = Path(capture["path"])
    engine = _ocr_engine()
    result, _ = engine(str(path))
    items: list[dict[str, Any]] = []
    for entry in result or []:
        if len(entry) < 3:
            continue
        box, text, confidence = entry[0], str(entry[1]), float(entry[2])
        if confidence < min_confidence or not text.strip():
            continue
        items.append({
            "text": text,
            "confidence": round(confidence, 4),
            "box": box,
        })
    return {
        "path": str(path),
        "count": len(items),
        "text": "\n".join(item["text"] for item in items),
        "items": items,
    }


def _ocr_engine() -> Any:
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as error:
            raise RuntimeError("Chưa cài RapidOCR.") from error
        _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE
