from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import uuid4


APP_ROOT = Path(os.environ.get("M_AUTO_PILOT_ROOT", Path(__file__).resolve().parent.parent)).resolve()
PROJECTS_DIR = APP_ROOT / "work" / "projects"
DONE_STAGE_STATUSES = {
    "completed",
    "skipped",
}


PIPELINE_STAGES = (
    "video_selected",
    "video_edit",
    "remove_hardsub",
    "transcribe",
    "translate",
    "tts",
    "merge_audio",
    "subtitle",
    "export",
)


DEFAULT_PROCESSING_SETTINGS = {
    "audio_mode": "keep",
    "original_volume_percent": 30,
    "crop_preset": "original",
    "video_scale_percent": 120,
    "video_position_x_percent": -1,
    "video_position_y_percent": 100,
    "playback_speed": 1.0,
    "subtitle_mode": "burn",
    "tts_fit_to_subtitle_slot": False,
    "tts_max_fit_speed": 1.20,
    "tts_voice_effect_preset": "none",
    "tts_voice_pitch_semitones": 0.0,
    "tts_voice_tempo": 1.0,
    "tts_voice_volume_percent": 250,
    "tts_run_mode": "quality",
    "tts_preview_segment_limit": 30,
    "remove_source_subtitle": False,
    "subtitle_x_percent": 5,
    "subtitle_y_percent": 78,
    "subtitle_width_percent": 90,
    "subtitle_height_percent": 18,
    "subtitle_font_scale_percent": 72,
    "remove_source_logo": False,
    "logo_x_percent": 78,
    "logo_y_percent": 0,
    "logo_width_percent": 22,
    "logo_height_percent": 14,
    "brand_logo_enabled": False,
    "brand_logo_path": "",
    "brand_logo_x_percent": 3,
    "brand_logo_y_percent": 3,
    "brand_logo_scale_percent": 30,
    "brand_logo_opacity_percent": 85,
    "brand_text_enabled": False,
    "brand_text": "",
    "brand_text_x_percent": 5,
    "brand_text_y_percent": 88,
    "brand_text_size": 36,
    "brand_text_color": "white",
    "brand_text_opacity_percent": 90,
    "brand_text_box_enabled": True,
    "brand_text_box_opacity_percent": 35,
    "brand_overlay_timing_enabled": False,
    "brand_overlay_start_seconds": 0.0,
    "brand_overlay_end_seconds": 0.0,
    "banner_rotation_interval_seconds": 0.0,
    "voice_profile_id": "nghitts:Ngọc Huyền (mới)",
}


def make_safe_name(name: str) -> str:
    safe_name = re.sub(
        r"[^a-zA-Z0-9._-]+",
        "_",
        name,
    ).strip("._")

    return safe_name[:80] or "project"


@dataclass
class VideoProject:
    id: str
    name: str
    source_video: str
    project_dir: str
    created_at: str
    updated_at: str
    stages: dict[str, str] = field(default_factory=dict)
    processing_settings: dict = field(default_factory=dict)

    @classmethod
    def create(cls, video_path: Path) -> "VideoProject":
        video_path = video_path.resolve()

        if not video_path.exists():
            raise FileNotFoundError(
                f"Không tìm thấy video: {video_path}"
            )

        PROJECTS_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        now = datetime.now()
        project_id = uuid4().hex[:8]

        folder_name = (
            f"{make_safe_name(video_path.stem)}_"
            f"{now:%Y%m%d_%H%M%S}_"
            f"{project_id}"
        )

        project_dir = PROJECTS_DIR / folder_name
        project_dir.mkdir(
            parents=True,
            exist_ok=False,
        )

        for folder_name in (
            "audio",
            "subtitles",
            "tts",
            "cleaned",
            "checkpoints",
            "logs",
            "output",
        ):
            (project_dir / folder_name).mkdir()

        stages = {
            stage: "pending"
            for stage in PIPELINE_STAGES
        }
        stages["video_selected"] = "completed"
        stages["remove_hardsub"] = "skipped"

        project = cls(
            id=project_id,
            name=video_path.name,
            source_video=str(video_path),
            project_dir=str(project_dir),
            created_at=now.isoformat(timespec="seconds"),
            updated_at=now.isoformat(timespec="seconds"),
            stages=stages,
            processing_settings=DEFAULT_PROCESSING_SETTINGS.copy(),
        )

        project.save()
        return project

    @property
    def metadata_path(self) -> Path:
        return Path(self.project_dir) / "project.json"

    @property
    def progress_percent(self) -> int:
        if not self.stages:
            return 0

        done = sum(
            status in DONE_STAGE_STATUSES
            for status in self.stages.values()
        )

        return round(
            done / len(self.stages) * 100
        )

    def save(self) -> None:
        self.updated_at = datetime.now().isoformat(
            timespec="seconds"
        )

        serialized = json.dumps(
            asdict(self),
            ensure_ascii=False,
            indent=2,
        )
        temporary_path = self.metadata_path.with_name(
            f".{self.metadata_path.name}.tmp"
        )
        temporary_path.write_text(
            serialized,
            encoding="utf-8",
        )
        temporary_path.replace(self.metadata_path)

    def update_processing_settings(
        self,
        *,
        audio_mode: str,
        original_volume_percent: int,
        crop_preset: str,
        video_scale_percent: int = 120,
        video_position_x_percent: int = -1,
        video_position_y_percent: int = 100,
        playback_speed: float = 1.0,
        subtitle_mode: str = "burn",
        tts_fit_to_subtitle_slot: bool = False,
        tts_max_fit_speed: float = 1.20,
        tts_voice_effect_preset: str = "none",
        tts_voice_pitch_semitones: float = 0.0,
        tts_voice_tempo: float = 1.0,
        tts_voice_volume_percent: int = 250,
        tts_run_mode: str = "quality",
        tts_preview_segment_limit: int = 30,
        remove_source_subtitle: bool = False,
        subtitle_x_percent: int = 5,
        subtitle_y_percent: int = 78,
        subtitle_width_percent: int = 90,
        subtitle_height_percent: int = 18,
        remove_source_logo: bool = False,
        logo_x_percent: int = 78,
        logo_y_percent: int = 0,
        logo_width_percent: int = 22,
        logo_height_percent: int = 14,
        brand_logo_enabled: bool = False,
        brand_logo_path: str = "",
        brand_logo_x_percent: int = 3,
        brand_logo_y_percent: int = 3,
        brand_logo_scale_percent: int = 30,
        brand_logo_opacity_percent: int = 85,
        brand_text_enabled: bool = False,
        brand_text: str = "",
        brand_text_x_percent: int = 5,
        brand_text_y_percent: int = 88,
        brand_text_size: int = 36,
        brand_text_color: str = "white",
        brand_text_opacity_percent: int = 90,
        brand_text_box_enabled: bool = True,
        brand_text_box_opacity_percent: int = 35,
        brand_overlay_timing_enabled: bool = False,
        brand_overlay_start_seconds: float = 0.0,
        brand_overlay_end_seconds: float = 0.0,
        voice_profile_id: str = "",
    ) -> None:
        clean_keys = (
            "remove_source_subtitle",
            "subtitle_x_percent",
            "subtitle_y_percent",
            "subtitle_width_percent",
            "subtitle_height_percent",
            "remove_source_logo",
            "logo_x_percent",
            "logo_y_percent",
            "logo_width_percent",
            "logo_height_percent",
        )
        old_clean_settings = {
            key: self.processing_settings.get(
                key,
                DEFAULT_PROCESSING_SETTINGS[key],
            )
            for key in clean_keys
        }
        new_clean_settings = {
            "remove_source_subtitle": remove_source_subtitle,
            "subtitle_x_percent": subtitle_x_percent,
            "subtitle_y_percent": subtitle_y_percent,
            "subtitle_width_percent": subtitle_width_percent,
            "subtitle_height_percent": subtitle_height_percent,
            "remove_source_logo": remove_source_logo,
            "logo_x_percent": logo_x_percent,
            "logo_y_percent": logo_y_percent,
            "logo_width_percent": logo_width_percent,
            "logo_height_percent": logo_height_percent,
        }
        clean_settings_changed = (
            old_clean_settings != new_clean_settings
        )
        merge_keys = (
            "tts_fit_to_subtitle_slot",
            "tts_max_fit_speed",
        )
        old_merge_settings = {
            key: self.processing_settings.get(
                key,
                DEFAULT_PROCESSING_SETTINGS[key],
            )
            for key in merge_keys
        }
        new_merge_settings = {
            "tts_fit_to_subtitle_slot": tts_fit_to_subtitle_slot,
            "tts_max_fit_speed": tts_max_fit_speed,
        }
        merge_settings_changed = (
            old_merge_settings != new_merge_settings
        )
        tts_effect_keys = (
            "tts_voice_effect_preset",
            "tts_voice_pitch_semitones",
            "tts_voice_tempo",
            "tts_voice_volume_percent",
            "tts_run_mode",
            "tts_preview_segment_limit",
        )
        old_tts_effect_settings = {
            key: self.processing_settings.get(
                key,
                DEFAULT_PROCESSING_SETTINGS[key],
            )
            for key in tts_effect_keys
        }
        new_tts_effect_settings = {
            "tts_voice_effect_preset": tts_voice_effect_preset,
            "tts_voice_pitch_semitones": tts_voice_pitch_semitones,
            "tts_voice_tempo": tts_voice_tempo,
            "tts_voice_volume_percent": tts_voice_volume_percent,
            "tts_run_mode": tts_run_mode,
            "tts_preview_segment_limit": tts_preview_segment_limit,
        }
        tts_effect_settings_changed = (
            old_tts_effect_settings != new_tts_effect_settings
        )
        brand_keys = (
            "brand_logo_enabled",
            "brand_logo_path",
            "brand_logo_x_percent",
            "brand_logo_y_percent",
            "brand_logo_scale_percent",
            "brand_logo_opacity_percent",
            "brand_text_enabled",
            "brand_text",
            "brand_text_x_percent",
            "brand_text_y_percent",
            "brand_text_size",
            "brand_text_color",
            "brand_text_opacity_percent",
            "brand_text_box_enabled",
            "brand_text_box_opacity_percent",
            "brand_overlay_timing_enabled",
            "brand_overlay_start_seconds",
            "brand_overlay_end_seconds",
        )
        old_brand_settings = {
            key: self.processing_settings.get(
                key,
                DEFAULT_PROCESSING_SETTINGS[key],
            )
            for key in brand_keys
        }
        new_brand_settings = {
            "brand_logo_enabled": brand_logo_enabled,
            "brand_logo_path": brand_logo_path,
            "brand_logo_x_percent": brand_logo_x_percent,
            "brand_logo_y_percent": brand_logo_y_percent,
            "brand_logo_scale_percent": brand_logo_scale_percent,
            "brand_logo_opacity_percent": brand_logo_opacity_percent,
            "brand_text_enabled": brand_text_enabled,
            "brand_text": brand_text,
            "brand_text_x_percent": brand_text_x_percent,
            "brand_text_y_percent": brand_text_y_percent,
            "brand_text_size": brand_text_size,
            "brand_text_color": brand_text_color,
            "brand_text_opacity_percent": brand_text_opacity_percent,
            "brand_text_box_enabled": brand_text_box_enabled,
            "brand_text_box_opacity_percent": brand_text_box_opacity_percent,
            "brand_overlay_timing_enabled": brand_overlay_timing_enabled,
            "brand_overlay_start_seconds": brand_overlay_start_seconds,
            "brand_overlay_end_seconds": brand_overlay_end_seconds,
        }
        brand_settings_changed = (
            old_brand_settings != new_brand_settings
        )
        old_voice_profile_id = str(
            self.processing_settings.get(
                "voice_profile_id",
                "",
            )
            or ""
        )
        voice_changed = old_voice_profile_id != voice_profile_id

        self.processing_settings.update(
            {
                "audio_mode": audio_mode,
                "original_volume_percent": original_volume_percent,
                "crop_preset": crop_preset,
                "video_scale_percent": video_scale_percent,
                "video_position_x_percent": video_position_x_percent,
                "video_position_y_percent": video_position_y_percent,
                "playback_speed": playback_speed,
                "subtitle_mode": subtitle_mode,
                "tts_fit_to_subtitle_slot": tts_fit_to_subtitle_slot,
                "tts_max_fit_speed": tts_max_fit_speed,
                **new_tts_effect_settings,
                "remove_source_subtitle": remove_source_subtitle,
                "subtitle_x_percent": subtitle_x_percent,
                "subtitle_y_percent": subtitle_y_percent,
                "subtitle_width_percent": subtitle_width_percent,
                "subtitle_height_percent": subtitle_height_percent,
                "remove_source_logo": remove_source_logo,
                "logo_x_percent": logo_x_percent,
                "logo_y_percent": logo_y_percent,
                "logo_width_percent": logo_width_percent,
                "logo_height_percent": logo_height_percent,
                "voice_profile_id": voice_profile_id,
                **new_brand_settings,
            }
        )
        self.stages["video_edit"] = "completed"
        clean_enabled = (
            remove_source_subtitle
            or remove_source_logo
        )

        if not clean_enabled:
            self.stages["remove_hardsub"] = "skipped"
        elif (
            clean_settings_changed
            or self.stages.get("remove_hardsub") not in (
                "completed",
                "running",
            )
        ):
            self.stages["remove_hardsub"] = "pending"

        if clean_settings_changed:
            for stage in (
                "transcribe",
                "translate",
                "tts",
                "merge_audio",
                "subtitle",
                "export",
            ):
                self.stages[stage] = "pending"

        if merge_settings_changed:
            for stage in (
                "merge_audio",
                "export",
            ):
                self.stages[stage] = "pending"

        if brand_settings_changed:
            self.stages["export"] = "pending"

        if voice_changed:
            for stage in (
                "tts",
                "merge_audio",
                "export",
            ):
                self.stages[stage] = "pending"

        if tts_effect_settings_changed:
            for stage in (
                "tts",
                "merge_audio",
                "export",
            ):
                self.stages[stage] = "pending"

        self.save()

    def sync_artifact_stages(
        self,
        *,
        save: bool = False,
    ) -> bool:
        project_dir = Path(self.project_dir)

        original_subtitle = (
            project_dir
            / "subtitles"
            / "original.srt"
        )
        translated_subtitle = (
            project_dir
            / "subtitles"
            / "original.translated.vi.srt"
        )
        tts_manifest = (
            project_dir
            / "tts"
            / "tts_manifest.json"
        )
        cleaned_video = (
            project_dir
            / "cleaned"
            / "cleaned.mp4"
        )
        merged_audio = (
            project_dir
            / "audio"
            / "vietnamese_voice.wav"
        )
        merged_audio_manifest = merged_audio.with_suffix(
            ".manifest.json"
        )

        def is_current(
            artifact_path: Path,
            *dependency_paths: Path,
        ) -> bool:
            if not artifact_path.exists():
                return False

            artifact_mtime = artifact_path.stat().st_mtime

            for dependency_path in dependency_paths:
                if not dependency_path.exists():
                    continue

                if artifact_mtime + 0.01 < dependency_path.stat().st_mtime:
                    return False

            return True

        remove_enabled = bool(
            self.processing_settings.get(
                "remove_source_subtitle",
                False,
            )
            or self.processing_settings.get(
                "remove_source_logo",
                False,
            )
        )
        cleaned_current = (
            remove_enabled
            and is_current(
                cleaned_video,
                Path(self.source_video),
            )
        )
        transcribe_current = (
            (not remove_enabled or cleaned_current)
            and is_current(
                original_subtitle,
                effective_source_video_path(self),
            )
        )
        translate_current = is_current(
            translated_subtitle,
            original_subtitle,
        )
        tts_current = (
            translate_current
            and is_current(
                tts_manifest,
                translated_subtitle,
            )
        )
        merge_audio_current = (
            tts_current
            and merged_audio.exists()
            and is_current(
                merged_audio_manifest,
                tts_manifest,
            )
        )

        stage_current = {
            "remove_hardsub": (
                cleaned_current
                if remove_enabled
                else True
            ),
            "transcribe": transcribe_current,
            "translate": translate_current,
            "tts": tts_current,
            "merge_audio": merge_audio_current,
        }

        changed = False

        if (
            not remove_enabled
            and self.stages.get("remove_hardsub") == "pending"
        ):
            self.stages["remove_hardsub"] = "skipped"
            changed = True

        for stage, current in stage_current.items():
            completed_status = (
                "skipped"
                if stage == "remove_hardsub"
                and not remove_enabled
                else "completed"
            )
            if (
                current
                and self.stages.get(stage) != completed_status
            ):
                self.stages[stage] = completed_status
                changed = True
            elif (
                not current
                and self.stages.get(stage) in DONE_STAGE_STATUSES
            ):
                self.stages[stage] = "pending"
                changed = True

        output_dir = project_dir / "output"
        exported_videos = (
            [
                path
                for path in output_dir.rglob("*.mp4")
                if path.is_file()
                and not path.is_relative_to(output_dir / "shorts")
            ]
            if output_dir.exists()
            else []
        )
        newest_export = (
            max(
                exported_videos,
                key=lambda path: path.stat().st_mtime,
            )
            if exported_videos
            else None
        )
        export_current = (
            newest_export is not None
            and merge_audio_current
            and is_current(
                newest_export,
                merged_audio,
                translated_subtitle,
            )
        )

        if (
            export_current
            and self.stages.get("export") != "completed"
        ):
            self.stages["export"] = "completed"
            changed = True
        elif (
            not export_current
            and self.stages.get("export") == "completed"
        ):
            self.stages["export"] = "pending"
            changed = True

        subtitle_mode = str(
            self.processing_settings.get(
                "subtitle_mode",
                "soft",
            )
        )

        if (
            subtitle_mode != "none"
            and export_current
            and translated_subtitle.exists()
            and self.stages.get("subtitle") != "completed"
        ):
            self.stages["subtitle"] = "completed"
            changed = True
        elif (
            (
                subtitle_mode == "none"
                or not export_current
                or not translated_subtitle.exists()
            )
            and self.stages.get("subtitle") == "completed"
        ):
            self.stages["subtitle"] = "pending"
            changed = True

        if changed and save:
            self.save()

        return changed

    @classmethod
    def load(
        cls,
        metadata_path: Path,
    ) -> "VideoProject":
        data = json.loads(
            metadata_path.read_text(
                encoding="utf-8"
            )
        )

        stages = data.get("stages", {})

        for stage in PIPELINE_STAGES:
            stages.setdefault(stage, "pending")

        if stages:
            stages["video_selected"] = "completed"

        settings = DEFAULT_PROCESSING_SETTINGS.copy()
        settings.update(
            data.get("processing_settings", {})
        )

        data["stages"] = stages
        data["processing_settings"] = settings

        project = cls(**data)
        project.sync_artifact_stages()

        return project


def load_all_projects() -> list[VideoProject]:
    PROJECTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    projects: list[VideoProject] = []

    for metadata_path in PROJECTS_DIR.glob(
        "*/project.json"
    ):
        try:
            projects.append(
                VideoProject.load(metadata_path)
            )
        except (
            OSError,
            ValueError,
            TypeError,
            json.JSONDecodeError,
        ):
            continue

    return sorted(
        projects,
        key=lambda project: project.updated_at,
        reverse=True,
    )


def delete_project(
    project: VideoProject,
) -> None:
    projects_root = PROJECTS_DIR.resolve()
    project_dir = Path(project.project_dir).resolve()

    if not project_dir.exists():
        return

    if not project_dir.is_relative_to(projects_root):
        raise ValueError(
            "Chỉ được xóa project nằm trong work/projects."
        )

    if project_dir == projects_root:
        raise ValueError(
            "Không thể xóa thư mục projects gốc."
        )

    shutil.rmtree(project_dir)


def cleaned_video_path(
    project: VideoProject,
) -> Path:
    return (
        Path(project.project_dir)
        / "cleaned"
        / "cleaned.mp4"
    )


def effective_source_video_path(
    project: VideoProject,
) -> Path:
    cleaned_path = cleaned_video_path(project)

    if (
        project.stages.get("remove_hardsub") == "completed"
        and cleaned_path.exists()
    ):
        return cleaned_path

    return Path(project.source_video)
