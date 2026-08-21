from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from downloader.cookie_store import CookieStore
from downloader.platform_config import (
    Platform,
    get_platform_config,
)


@dataclass(frozen=True)
class SessionStatus:
    platform: Platform
    display_name: str
    cookie_path: Path
    available: bool
    cookie_size: int
    imported_count: int | None
    matching_domain_count: int | None


class SessionManager:
    """
    Quản lý phiên đăng nhập của các nền tảng.

    Phiên bản hiện tại sử dụng một cookie mặc định cho mỗi nền tảng.
    Sau này có thể mở rộng sang nhiều tài khoản mà không cần sửa
    VideoDownloader.
    """

    def __init__(
        self,
        store: CookieStore | None = None,
    ) -> None:
        self.store = store or CookieStore()

    def get_status(
        self,
        platform: Platform,
    ) -> SessionStatus:
        config = get_platform_config(platform)
        cookie_path = self.store.cookie_file(platform)

        available = self._is_cookie_file_valid(
            cookie_path
        )

        cookie_size = (
            cookie_path.stat().st_size
            if cookie_path.exists()
            else 0
        )

        imported_count: int | None = None
        matching_domain_count: int | None = None

        metadata = self._read_metadata(platform)

        if metadata is not None:
            imported_count = self._safe_int(
                metadata.get("imported_count")
            )
            matching_domain_count = self._safe_int(
                metadata.get("matching_domain_count")
            )

        return SessionStatus(
            platform=platform,
            display_name=config.display_name,
            cookie_path=cookie_path,
            available=available,
            cookie_size=cookie_size,
            imported_count=imported_count,
            matching_domain_count=matching_domain_count,
        )

    def require_cookie(
        self,
        platform: Platform,
    ) -> Path:
        status = self.get_status(platform)

        if not status.available:
            raise RuntimeError(
                f"Chưa có phiên đăng nhập hợp lệ cho "
                f"{status.display_name}.\n\n"
                "Hãy nhập lại file cookie trong phần "
                "cài đặt Downloader."
            )

        return status.cookie_path.resolve()

    def remove_session(
        self,
        platform: Platform,
    ) -> None:
        self.store.remove(platform)

    def has_session(
        self,
        platform: Platform,
    ) -> bool:
        return self.get_status(platform).available

    def _read_metadata(
        self,
        platform: Platform,
    ) -> dict[str, Any] | None:
        metadata_path = self.store.metadata_file(
            platform
        )

        if not metadata_path.exists():
            return None

        try:
            payload = json.loads(
                metadata_path.read_text(
                    encoding="utf-8",
                )
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ):
            return None

        if not isinstance(payload, dict):
            return None

        return payload

    @staticmethod
    def _is_cookie_file_valid(
        cookie_path: Path,
    ) -> bool:
        if not cookie_path.exists():
            return False

        if not cookie_path.is_file():
            return False

        if cookie_path.stat().st_size == 0:
            return False

        try:
            first_lines = cookie_path.read_text(
                encoding="utf-8-sig",
                errors="replace",
            )[:500]
        except OSError:
            return False

        return (
            "Netscape HTTP Cookie File"
            in first_lines
            or "HTTP Cookie File" in first_lines
        )

    @staticmethod
    def _safe_int(
        value: object,
    ) -> int | None:
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None