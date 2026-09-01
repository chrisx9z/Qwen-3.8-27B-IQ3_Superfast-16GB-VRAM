from __future__ import annotations

import sys
import subprocess
import json
from typing import Any

ALLOWED_KEYS = {
    "ENTER", "ESC", "TAB", "BACKSPACE", "DELETE", "SPACE",
    "UP", "DOWN", "LEFT", "RIGHT",
    "CTRL+A", "CTRL+C", "CTRL+V", "CTRL+S", "ALT+F4", "CMD+C", "CMD+V", "CMD+A", "CMD+S", "CMD+Q",
}

IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"


def _run_applescript(script: str) -> str:
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
        return res.stdout.strip()
    except Exception:
        return ""


def ui_list_windows(limit: int = 50) -> dict[str, Any]:
    if IS_MACOS:
        script = """
        tell application "System Events"
            set procList to every process whose visible is true
            set winInfoList to {}
            repeat with proc in procList
                set procName to name of proc
                set winList to every window of proc
                repeat with win in winList
                    set end of winInfoList to (procName & " - " & (name of win))
                end repeat
            end repeat
            return winInfoList
        end tell
        """
        raw = _run_applescript(script)
        lines = [item.strip() for item in raw.split(",") if item.strip()]
        windows = [{"title": title, "class_name": "NSWindow", "process_id": 0} for title in lines[:limit]]
        return {"count": len(windows), "windows": windows}
    
    # Windows fallback
    try:
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
    except Exception as e:
        return {"count": 0, "windows": [], "error": str(e)}


def ui_snapshot(window_title: str, limit: int = 100) -> dict[str, Any]:
    if IS_MACOS:
        script = f"""
        tell application "System Events"
            set winElemList to {{}}
            try
                tell process "{window_title}"
                    set uieList to every UI element of front window
                    repeat with elem in uieList
                        set end of winElemList to (description of elem & ": " & (name of elem as text))
                    end repeat
                end tell
            end try
            return winElemList
        end tell
        """
        raw = _run_applescript(script)
        elems = [item.strip() for item in raw.split(",") if item.strip()]
        controls = [{"title": e, "control_type": "NSControl", "automation_id": e} for e in elems[:limit]]
        return {
            "window_title": window_title,
            "count": len(controls),
            "controls": controls,
        }

    try:
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
    except Exception as e:
        return {"window_title": window_title, "count": 0, "controls": [], "error": str(e)}


def ui_click(
    window_title: str,
    *,
    control_title: str = "",
    automation_id: str = "",
    control_type: str = "",
) -> dict[str, Any]:
    if IS_MACOS:
        try:
            import pyautogui
            script = f"""
            tell application "System Events"
                tell process "{window_title}"
                    set frontmost to true
                    click button "{control_title or automation_id}" of front window
                end tell
            end tell
            """
            _run_applescript(script)
            return {"clicked": True, "control": {"title": control_title or automation_id}}
        except Exception:
            return {"clicked": False, "error": "Could not click UI control on macOS"}

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
    if IS_MACOS:
        try:
            import pyautogui
            # Switch to app
            subprocess.run(["open", "-a", window_title], capture_output=True)
            pyautogui.write(value, interval=0.01)
            if press_enter:
                pyautogui.press("enter")
            return {"typed": True, "value": value}
        except Exception:
            safe_val = value.replace('"', '\"')
            enter_clause = 'keystroke return\n' if press_enter else ''
            script = f"""
            tell application "System Events"
                tell process "{window_title}"
                    set frontmost to true
                    keystroke "{safe_val}"
                    {enter_clause}
                end tell
            end tell
            """
            _run_applescript(script)
            return {"typed": True, "value": value}

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
    
    if IS_MACOS:
        try:
            import pyautogui
            key_map = {"ENTER": "enter", "ESC": "esc", "TAB": "tab", "BACKSPACE": "backspace", "DELETE": "delete", "SPACE": "space"}
            k = key_map.get(normalized, normalized.lower())
            pyautogui.press(k)
            return {"pressed": normalized}
        except Exception:
            pass

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
    if window_title.strip() and not IS_MACOS:
        try:
            win = _window(window_title)
            rect = win.rectangle()
            bbox_kwargs = {
                "x": max(0, rect.left),
                "y": max(0, rect.top),
                "width": max(10, rect.width()),
                "height": max(10, rect.height()),
            }
            offset_x, offset_y = max(0, rect.left), max(0, rect.top)
        except Exception:
            pass

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

    if IS_MACOS:
        try:
            import pyautogui
            screen_w, screen_h = pyautogui.size()
            from PIL import ImageGrab
            sample_img = ImageGrab.grab()
            scale_x = sample_img.width / screen_w if screen_w > 0 else 1.0
            scale_y = sample_img.height / screen_h if screen_h > 0 else 1.0
            if scale_x > 1.2:
                cx = int(cx / scale_x)
                cy = int(cy / scale_y)
            pyautogui.click(cx, cy)
        except Exception:
            pass
    elif IS_WINDOWS:
        try:
            import pyautogui
            pyautogui.click(cx, cy)
        except Exception:
            try:
                import ctypes
                ctypes.windll.user32.SetCursorPos(cx, cy)
                ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
            except Exception:
                pass

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
        return Desktop(backend="uia")
    except ImportError:
        return None


def _window(title: str) -> Any:
    value = str(title or "").strip()
    if not value:
        raise ValueError("window_title không được để trống.")
    d = _desktop()
    if d is None:
        raise RuntimeError("Windows Desktop not available on this platform.")
    window = d.window(title=value)
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
