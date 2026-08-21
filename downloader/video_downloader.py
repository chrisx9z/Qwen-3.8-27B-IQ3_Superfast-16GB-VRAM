from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from downloader.platform_config import (
    Platform,
    detect_platform,
    get_platform_config,
)
from downloader.session_manager import SessionManager


ProgressCallback = Callable[[str], None]
ProcessCallback = Callable[[subprocess.Popen[str]], None]
CancelCheck = Callable[[], bool]


@dataclass(frozen=True)
class DownloadRequest:
    url: str
    output_dir: Path
    max_height: int | None = None
    prefer_h264: bool = False
    use_cookie: bool = True

    use_aria2: bool = True
    aria2_connections: int = 16
    concurrent_fragments: int = 8
    download_playlist: bool = False
    playlist_dir_name: str | None = None
    batch_urls: list[str] | None = None
    batch_name: str | None = None


@dataclass(frozen=True)
class DownloadResult:
    platform: Platform
    video_path: Path
    has_video: bool
    has_audio: bool
    metadata_path: Path | None
    video_paths: list[Path] = None
    playlist_dir: Path | None = None


class VideoDownloader:
    def __init__(
        self,
        *,
        session_manager: SessionManager | None = None,
        ffprobe_path: str | None = None,
        progress_callback: ProgressCallback | None = None,
        process_callback: ProcessCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> None:
        self.session_manager = (
            session_manager or SessionManager()
        )

        self.ffprobe_path = (
            ffprobe_path
            or shutil.which("ffprobe")
            or ""
        )

        self.progress_callback = progress_callback
        self.process_callback = process_callback
        self.cancel_check = cancel_check

    def download(
        self,
        request: DownloadRequest,
    ) -> DownloadResult:
        url = request.url.strip()
        request_urls = [
            item.strip()
            for item in (request.batch_urls or [])
            if item.strip()
        ]

        self._validate_request(
            url=url,
            request=request,
        )

        platform = detect_platform(
            request_urls[0] if request_urls else url
        )

        if platform is None:
            raise ValueError(
                "URL không thuộc Bilibili, Douyin "
                "hoặc RedNote."
            )

        config = get_platform_config(platform)

        output_dir = request.output_dir.resolve()

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._report(
            f"Đã nhận diện nguồn: {config.display_name}"
        )

        command = self._build_command(
            platform=platform,
            request=request,
            output_dir=output_dir,
        )

        self._report(
            "Đang tải video và âm thanh..."
        )

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            **self._hidden_subprocess_kwargs(),
        )
        if self.process_callback is not None:
             self.process_callback(process)

        output_lines: list[str] = []

        if process.stdout is not None:
            for raw_line in process.stdout:

                if (
                    self.cancel_check is not None
                    and self.cancel_check()
                ):
                    process.terminate()

                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()

                    raise RuntimeError(
                        "Quá trình tải đã bị hủy."
                    )

                line = raw_line.rstrip()

                if not line:
                    continue

                output_lines.append(line)
                self._report(line)

        return_code = process.wait()
        complete_output = "\n".join(output_lines)

        if return_code != 0:
            raise RuntimeError(
                "Không thể tải video.\n\n"
                f"Nguồn: {config.display_name}\n\n"
                f"Chi tiết:\n"
                f"{complete_output[-6000:]}"
            )

        output_search_dir = self._request_output_search_dir(
            request=request,
            output_dir=output_dir,
        )
        video_paths = self._find_output_paths(
            output_text=complete_output,
            output_dir=output_search_dir,
        )
        video_path = video_paths[0]

        self._report(
            "Đang kiểm tra file bằng ffprobe..."
        )

        for current_video_path in video_paths:
            has_video, has_audio = self.probe_streams(
                current_video_path
            )

            if not has_video:
                raise RuntimeError(
                    "File đã tải không có luồng hình ảnh:\n"
                    f"{current_video_path}"
                )

            if not has_audio:
                raise RuntimeError(
                    "File đã tải không có luồng âm thanh.\n"
                    "Không thể đưa file này sang Whisper.\n\n"
                    f"{current_video_path}"
                )

        metadata_path = video_path.with_suffix(
            ".info.json"
        )

        if not metadata_path.exists():
            metadata_path = None

        self._report(
            "Hoàn tất: file có đầy đủ hình và tiếng."
        )

        return DownloadResult(
            platform=platform,
            video_path=video_path,
            has_video=has_video,
            has_audio=has_audio,
            metadata_path=metadata_path,
            video_paths=video_paths,
            playlist_dir=video_path.parent if len(video_paths) > 1 else None,
        )

    def _build_command(
        self,
        *,
        platform: Platform,
        request: DownloadRequest,
        output_dir: Path,
    ) -> list[str]:
        if request.batch_urls:
            batch_name = self._safe_folder_name(
                request.batch_name or "batch"
            )
            output_template = str(
                output_dir
                / batch_name
                / "%(autonumber)03d - %(title).160B [%(id)s].%(ext)s"
            )
        elif request.download_playlist:
            playlist_dir_name = self._safe_folder_name(
                request.playlist_dir_name
                or "%(playlist_title).120B"
            )
            output_template = str(
                output_dir
                / playlist_dir_name
                / "%(playlist_index)03d - %(title).160B [%(id)s].%(ext)s"
            )
        else:
            output_template = str(
                output_dir
                / "%(title).180B [%(id)s].%(ext)s"
            )

        command = [
            sys.executable,
            "-m",
            "yt_dlp",

            "--newline",
            "--progress",

            "--concurrent-fragments",
            str(
                max(
                    1,
                    min(request.concurrent_fragments, 16),
                )
            ),

            "--retries",
            "10",

            "--fragment-retries",
            "10",

            "--windows-filenames",
            "--merge-output-format",
            "mp4",
            "--write-info-json",
            "--no-write-playlist-metafiles",
            "--print",
            "after_move:filepath",
            "-f",
            self._build_format_selector(request),
            "-o",
            output_template,
        ]
        if request.batch_urls:
            command.append("--no-playlist")
            command.extend(
                [
                    "--autonumber-start",
                    "1",
                ]
            )
        elif request.download_playlist:
            command.append("--yes-playlist")
        else:
            command.append("--no-playlist")
        if request.use_aria2:
            aria2c_path = self._find_aria2c()

            if not aria2c_path:
                self._report(
                    "Không tìm thấy aria2c. "
                    "Tự chuyển sang chế độ tải thường bằng yt-dlp."
                )
            else:
                connections = max(
                    1,
                    min(request.aria2_connections, 32),
                )

                command.extend(
                    [
                        "--downloader",
                        aria2c_path,
                        "--downloader-args",
                        (
                            f"aria2c:-x {connections} "
                            f"-s {connections} "
                            "-k 1M "
                            "--file-allocation=none "
                            "--summary-interval=1"
                        ),
                    ]
                )

        if request.use_cookie:
            cookie_path = (
                self.session_manager.require_cookie(
                    platform
                )
            )

            command.extend(
                [
                    "--cookies",
                    str(cookie_path),
                ]
            )

        if request.batch_urls:
            command.extend(
                url.strip()
                for url in request.batch_urls
                if url.strip()
            )
        else:
            command.append(request.url.strip())

        return command

    @staticmethod
    def _request_output_search_dir(
        *,
        request: DownloadRequest,
        output_dir: Path,
    ) -> Path:
        if request.batch_urls:
            return (
                output_dir
                / VideoDownloader._safe_folder_name(
                    request.batch_name or "batch"
                )
            ).resolve()

        if request.download_playlist:
            return (
                output_dir
                / VideoDownloader._safe_folder_name(
                    request.playlist_dir_name
                    or "%(playlist_title).120B"
                )
            ).resolve()

        return output_dir

    def probe_streams(
        self,
        video_path: Path,
    ) -> tuple[bool, bool]:
        if not self.ffprobe_path:
            raise RuntimeError(
                "Không tìm thấy ffprobe.\n"
                "Hãy cài FFmpeg hoặc thêm ffprobe "
                "vào PATH."
            )

        command = [
            self.ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "json",
            str(video_path),
        ]

        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **VideoDownloader._hidden_subprocess_kwargs(),
        )

        if process.returncode != 0:
            raise RuntimeError(
                "Không thể kiểm tra file video.\n\n"
                f"{process.stderr.strip()}"
            )

        try:
            payload = json.loads(
                process.stdout or "{}"
            )
        except json.JSONDecodeError as error:
            raise RuntimeError(
                "ffprobe trả về dữ liệu không hợp lệ."
            ) from error

        codec_types = {
            str(stream.get("codec_type", ""))
            for stream in payload.get(
                "streams",
                [],
            )
        }

        return (
            "video" in codec_types,
            "audio" in codec_types,
        )

    @staticmethod
    def _find_aria2c() -> str | None:
        aria2c_path = shutil.which("aria2c")

        if aria2c_path:
            return aria2c_path

        local_app_data = os.environ.get(
            "LOCALAPPDATA",
            "",
        )

        if not local_app_data:
            return None

        packages_dir = (
            Path(local_app_data)
            / "Microsoft"
            / "WinGet"
            / "Packages"
        )

        candidates = sorted(
            packages_dir.glob(
                "aria2.aria2_*/*/aria2c.exe"
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

        if candidates:
            return str(candidates[0])

        return None

    @staticmethod
    def _build_format_selector(
        request: DownloadRequest,
    ) -> str:
        height_filter = ""

        if request.max_height is not None:
            height_filter = (
                f"[height<={request.max_height}]"
            )

        if request.prefer_h264:
            return (
                f"bestvideo{height_filter}"
                f"[vcodec^=avc1]+bestaudio/"
                f"bestvideo{height_filter}+bestaudio/"
                f"best{height_filter}/best"
            )

        return (
            f"bestvideo{height_filter}+bestaudio/"
            f"best{height_filter}/best"
        )

    @staticmethod
    def _find_output_path(
        *,
        output_text: str,
        output_dir: Path,
    ) -> Path:
        return VideoDownloader._find_output_paths(
            output_text=output_text,
            output_dir=output_dir,
        )[0]

    @staticmethod
    def _find_output_paths(
        *,
        output_text: str,
        output_dir: Path,
    ) -> list[Path]:
        supported_extensions = {
            ".mp4",
            ".mkv",
            ".webm",
            ".mov",
        }

        output_paths: list[Path] = []

        for line in output_text.splitlines():
            candidate_text = line.strip().strip('"')

            if not candidate_text:
                continue

            candidate = Path(candidate_text)

            if candidate.is_absolute():
                resolved = candidate.resolve()
            else:
                resolved = (
                    output_dir / candidate
                ).resolve()

            if re.search(
                r"\.f\d+$",
                resolved.stem,
                re.IGNORECASE,
            ):
                continue

            if (
                resolved.exists()
                and resolved.is_file()
                and resolved.suffix.lower()
                in supported_extensions
            ):
                output_paths.append(resolved)

        if output_paths:
            unique_paths = []
            seen_paths = set()

            for path in output_paths:
                resolved = path.resolve()

                if resolved in seen_paths:
                    continue

                unique_paths.append(resolved)
                seen_paths.add(resolved)

            return sorted(
                unique_paths,
                key=VideoDownloader._playlist_sort_key,
            )

        media_files = sorted(
            (
                path
                for path in output_dir.rglob("*")
                if path.is_file()
                and path.suffix.lower()
                in supported_extensions
            ),
            key=VideoDownloader._playlist_sort_key,
        )

        if media_files:
            return [
                path.resolve()
                for path in media_files
            ]

        raise RuntimeError(
            "yt-dlp báo hoàn tất nhưng không tìm thấy "
            "file video đầu ra."
        )

    @staticmethod
    def _hidden_subprocess_kwargs() -> dict[str, int]:
        if os.name != "nt":
            return {}

        return {
            "creationflags": subprocess.CREATE_NO_WINDOW,
        }

    @staticmethod
    def _playlist_sort_key(path: Path) -> tuple[int, str]:
        match = re.match(
            r"^\s*(\d+)",
            path.stem,
        )

        if match is not None:
            return (
                int(match.group(1)),
                path.name.lower(),
            )

        return (
            999999,
            path.name.lower(),
        )

    @staticmethod
    def _validate_request(
        *,
        url: str,
        request: DownloadRequest,
    ) -> None:
        batch_urls = [
            item.strip()
            for item in (request.batch_urls or [])
            if item.strip()
        ]

        if not url and not batch_urls:
            raise ValueError(
                "URL video không được để trống."
            )

        urls_to_check = batch_urls or [url]

        if any(
            not item.startswith(
                ("http://", "https://")
            )
            for item in urls_to_check
        ):
            raise ValueError(
                "URL video không hợp lệ."
            )

        if (
            request.max_height is not None
            and request.max_height < 144
        ):
            raise ValueError(
                "Độ phân giải tối đa không hợp lệ."
            )

    @staticmethod
    def _safe_folder_name(
        text: str,
    ) -> str:
        cleaned = re.sub(
            r'[<>:"/\\|?*\x00-\x1f]+',
            "_",
            text.strip(),
        )
        cleaned = re.sub(
            r"\s+",
            " ",
            cleaned,
        ).strip(" .")
        return cleaned[:120] or "batch"

    def _report(
        self,
        message: str,
    ) -> None:
        if self.progress_callback is not None:
            self.progress_callback(message)
