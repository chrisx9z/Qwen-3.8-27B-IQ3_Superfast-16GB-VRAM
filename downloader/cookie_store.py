from __future__ import annotations

import shutil
from pathlib import Path

from downloader.platform_config import Platform


class CookieStore:
    def __init__(
        self,
        root: Path | str | None = None,
    ) -> None:
        self.root = (
            Path(root)
            if root is not None
            else Path(__file__).resolve().parents[1]
            / "data"
            / "cookies"
        )

    def ensure(self) -> None:
        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

    def cookie_file(
        self,
        platform: Platform,
    ) -> Path:
        self.ensure()
        return self.root / f"{platform.value}.txt"

    def metadata_file(
        self,
        platform: Platform,
    ) -> Path:
        self.ensure()
        return self.root / f"{platform.value}.json"

    def exists(
        self,
        platform: Platform,
    ) -> bool:
        path = self.cookie_file(platform)

        return (
            path.exists()
            and path.is_file()
            and path.stat().st_size > 0
        )

    def remove(
        self,
        platform: Platform,
    ) -> None:
        for path in (
            self.cookie_file(platform),
            self.metadata_file(platform),
        ):
            if path.exists():
                path.unlink()

    def copy_cookie_file(
        self,
        platform: Platform,
        source_path: Path | str,
    ) -> Path:
        source = Path(source_path)

        if not source.exists():
            raise FileNotFoundError(
                f"Không tìm thấy file cookie: {source}"
            )

        if not source.is_file():
            raise ValueError(
                "Đường dẫn cookie không phải là một file."
            )

        destination = self.cookie_file(platform)

        shutil.copy2(
            source,
            destination,
        )

        return destination
