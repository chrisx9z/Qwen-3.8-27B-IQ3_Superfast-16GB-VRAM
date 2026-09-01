from __future__ import annotations

from typing import Any


ALLOWED_KEYS = {
    "ENTER",
    "ESC",
    "TAB",
    "BACKSPACE",
    "DELETE",
    "SPACE",
    "UP",
    "DOWN",
    "LEFT",
    "RIGHT",
    "CTRL+A",
    "CTRL+C",
    "CTRL+V",
    "CTRL+S",
    "ALT+F4",
}


def ui_list_windows(limit: int = 50) -> dict[str, Any]:
    desktop = _desktop()
    windows: list[dict[str, Any]] = []
    for window in desktop.windows(visible_only=True):
        if len(windows) >= max(1, min(limit, 100)):
            break
        title = _call(window, "window_text")
        if not title:
            continue
        windows.append({
            "title": title,
            "class_name": _property(window, "class_name"),
            "process_id": _property(window, "process_id"),
        })
    return {"count": len(windows), "windows": windows}


def ui_snapshot(
    window_title: str,
    limit: int = 100,
) -> dict[str, Any]:
    window = _window(window_title)
    controls: list[dict[str, Any]] = []
    for control in window.descendants():
        if len(controls) >= max(1, min(limit, 200)):
            break
        title = _call(control, "window_text")
        control_type = _property(control, "control_type")
        automation_id = _property(control, "automation_id")
        if not title and not automation_id:
            continue
        controls.append({
            "title": title,
            "control_type": control_type,
            "automation_id": automation_id,
            "class_name": _property(control, "class_name"),
        })
    return {
        "window_title": _call(window, "window_text"),
        "count": len(controls),
        "controls": controls,
    }


def ui_click(
    window_title: str,
    *,
    control_title: str = "",
    automation_id: str = "",
    control_type: str = "",
) -> dict[str, Any]:
    control = _control(
        window_title,
        control_title=control_title,
        automation_id=automation_id,
        control_type=control_type,
    )
    try:
        control.click_input()
    except Exception:
        control.click()
    return {"clicked": True, "control": _control_summary(control)}


def ui_type(
    window_title: str,
    value: str,
    *,
    control_title: str = "",
    automation_id: str = "",
    control_type: str = "Edit",
    press_enter: bool = False,
) -> dict[str, Any]:
    control = _control(
        window_title,
        control_title=control_title,
        automation_id=automation_id,
        control_type=control_type,
    )
    try:
        control.set_edit_text(value)
    except Exception:
        control.click_input()
        control.type_keys(value, with_spaces=True)
    if press_enter:
        control.type_keys("{ENTER}")
    return {"typed": True, "control": _control_summary(control)}


def ui_press_key(
    window_title: str,
    key: str,
    *,
    control_title: str = "",
    automation_id: str = "",
    control_type: str = "",
) -> dict[str, Any]:
    normalized = str(key or "").strip().upper()
    if normalized not in ALLOWED_KEYS:
        raise ValueError(f"Phím không được phép: {normalized}")
    target = (
        _control(
            window_title,
            control_title=control_title,
            automation_id=automation_id,
            control_type=control_type,
        )
        if control_title or automation_id
        else _window(window_title)
    )
    target.type_keys("{" + normalized + "}")
    return {"pressed": normalized}


def ui_click_text(
    text: str,
    *,
    window_title: str = "",
    occurrence: int = 1,
    case_sensitive: bool = False,
    min_confidence: float = 0.35,
) -> dict[str, Any]:
    """Tìm text trên màn hình/cửa sổ qua OCR và kích chuột vào tọa độ tìm được."""
    query = str(text or "").strip()
    if not query:
        raise ValueError("text không được để trống.")

    from agent.screen_tools import screen_ocr

    offset_x, offset_y = 0, 0
    bbox_kwargs: dict[str, Any] = {}
    if window_title.strip():
        win = _window(window_title)
        rect = win.rectangle()
        bbox_kwargs = {
            "x": max(0, rect.left),
            "y": max(0, rect.top),
            "width": max(10, rect.width()),
            "height": max(10, rect.height()),
        }
        offset_x, offset_y = max(0, rect.left), max(0, rect.top)

    ocr_res = screen_ocr(min_confidence=min_confidence, **bbox_kwargs)
    items = ocr_res.get("items", [])

    matches = []
    needle = query if case_sensitive else query.lower()
    for item in items:
        item_text = item["text"] if case_sensitive else item["text"].lower()
        if needle in item_text:
            matches.append(item)

    if not matches:
        raise RuntimeError(
            f"Không tìm thấy text '{query}' trên "
            f"{'cửa sổ ' + window_title if window_title else 'màn hình'} qua OCR."
        )

    idx = max(1, min(occurrence, len(matches))) - 1
    target = matches[idx]
    box = target["box"]

    if isinstance(box, (list, tuple)) and len(box) >= 4 and isinstance(box[0], (list, tuple)):
        cx = int(sum(pt[0] for pt in box[:4]) / 4) + offset_x
        cy = int(sum(pt[1] for pt in box[:4]) / 4) + offset_y
    elif isinstance(box, (list, tuple)) and len(box) == 4:
        cx = int((box[0] + box[2]) / 2) + offset_x
        cy = int((box[1] + box[3]) / 2) + offset_y
    else:
        raise ValueError("Định dạng bounding box không hợp lệ.")

    try:
        from pywinauto import mouse

        mouse.click(button="left", coords=(cx, cy))
    except Exception:
        import ctypes

        ctypes.windll.user32.SetCursorPos(cx, cy)
        ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
        ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)

    return {
        "clicked": True,
        "matched_text": target["text"],
        "coords": [cx, cy],
        "confidence": target.get("confidence", 1.0),
        "occurrence": idx + 1,
        "total_matches": len(matches),
    }



def _desktop() -> Any:
    try:
        from pywinauto import Desktop
    except ImportError as error:
        raise RuntimeError("Chưa cài pywinauto cho Windows UI Automation.") from error
    return Desktop(backend="uia")


def _window(title: str) -> Any:
    value = str(title or "").strip()
    if not value:
        raise ValueError("window_title không được để trống.")
    window = _desktop().window(title=value)
    window.wait("exists", timeout=10)
    return window.wrapper_object()


def _control(
    window_title: str,
    *,
    control_title: str,
    automation_id: str,
    control_type: str,
) -> Any:
    if not control_title and not automation_id:
        raise ValueError("Cần control_title hoặc automation_id.")
    window = _window(window_title)
    criteria: dict[str, str] = {}
    if control_title:
        criteria["title"] = control_title
    if automation_id:
        criteria["auto_id"] = automation_id
    if control_type:
        criteria["control_type"] = control_type
    control = window.child_window(**criteria)
    control.wait("exists", timeout=10)
    return control.wrapper_object()


def _control_summary(control: Any) -> dict[str, Any]:
    return {
        "title": _call(control, "window_text"),
        "control_type": _property(control, "control_type"),
        "automation_id": _property(control, "automation_id"),
    }


def _call(value: Any, name: str) -> Any:
    try:
        return getattr(value, name)() or ""
    except Exception:
        return ""


def _property(value: Any, name: str) -> Any:
    try:
        return getattr(value.element_info, name) or ""
    except Exception:
        return ""
