"""Tải một file GGUF từ HuggingFace Hub (có resume + ghi tiến trình ra JSON).

Dùng bởi adapter OBLITERATUS của M Auto Pilot để lấy model đã abliterate.

Cách dùng:
    python hf_download_gguf.py <repo_id> <filename> <dest_dir> <progress_json> [revision]
"""

from __future__ import annotations

import json
import sys
import threading
import time
from datetime import datetime
from pathlib import Path


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _write(progress_path: Path, payload: dict) -> None:
    tmp = progress_path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(progress_path)
    except OSError:
        pass


def _expected_size(repo_id: str, filename: str) -> int | None:
    try:
        from huggingface_hub import HfApi

        info = HfApi().model_info(repo_id, files_metadata=True)
        for sibling in info.siblings or []:
            if sibling.rfilename == filename and sibling.size:
                return int(sibling.size)
    except Exception:  # noqa: BLE001
        return None
    return None


def _poll(progress_path: Path, dest_dir: Path, filename: str, expected: int | None, stop: threading.Event) -> None:
    target = dest_dir / filename
    while not stop.is_set():
        downloaded = 0
        if target.is_file():
            downloaded = target.stat().st_size
        if downloaded == 0:
            # huggingface_hub ghi file tạm .incomplete trong cache của local_dir
            for candidate in dest_dir.rglob("*.incomplete"):
                try:
                    downloaded += candidate.stat().st_size
                except OSError:
                    continue
        payload = {
            "status": "downloading",
            "updated_at": _now(),
            "downloaded_bytes": downloaded,
            "downloaded_gb": round(downloaded / 1024**3, 2),
            "expected_bytes": expected,
            "expected_gb": round(expected / 1024**3, 2) if expected else None,
            "percent": round(downloaded * 100 / expected, 1) if expected else None,
        }
        existing = {}
        try:
            existing = json.loads(progress_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = {}
        payload = {**existing, **payload}
        _write(progress_path, payload)
        stop.wait(3)


def main() -> int:
    if len(sys.argv) < 5:
        print(__doc__)
        return 2

    repo_id, filename, dest_raw, progress_raw = sys.argv[1:5]
    revision = sys.argv[5] if len(sys.argv) > 5 else "main"
    dest_dir = Path(dest_raw).expanduser()
    dest_dir.mkdir(parents=True, exist_ok=True)
    progress_path = Path(progress_raw).expanduser()
    progress_path.parent.mkdir(parents=True, exist_ok=True)

    expected = _expected_size(repo_id, filename)
    _write(progress_path, {
        "status": "starting",
        "repo": repo_id,
        "filename": filename,
        "dest_dir": str(dest_dir),
        "expected_bytes": expected,
        "expected_gb": round(expected / 1024**3, 2) if expected else None,
        "started_at": _now(),
        "pid": None,
    })

    stop = threading.Event()
    watcher = threading.Thread(
        target=_poll,
        args=(progress_path, dest_dir, filename, expected, stop),
        daemon=True,
    )
    watcher.start()

    try:
        from huggingface_hub import hf_hub_download

        path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            revision=revision,
            local_dir=str(dest_dir),
        )
    except Exception as error:  # noqa: BLE001
        stop.set()
        _write(progress_path, {
            "status": "error",
            "repo": repo_id,
            "filename": filename,
            "error": f"{type(error).__name__}: {error}",
            "finished_at": _now(),
        })
        print(f"ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        return 1

    stop.set()
    size = Path(path).stat().st_size if Path(path).is_file() else 0
    _write(progress_path, {
        "status": "completed",
        "repo": repo_id,
        "filename": filename,
        "path": str(path),
        "bytes": size,
        "gb": round(size / 1024**3, 2),
        "finished_at": _now(),
    })
    print(f"OK: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
