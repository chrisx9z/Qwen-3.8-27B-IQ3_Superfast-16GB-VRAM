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


def make_safe_name(name: str) -> str:
    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("._")
    return safe_name[:80] or "workspace_project"


@dataclass
class WorkspaceProject:
    id: str
    name: str
    project_dir: str
    created_at: str
    updated_at: str
    metadata: dict = field(default_factory=dict)
    source_video: str = ""
    stages: dict = field(default_factory=dict)
    processing_settings: dict = field(default_factory=dict)

    @classmethod
    def create(cls, name: str) -> WorkspaceProject:
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        project_id = uuid4().hex[:8]
        folder_name = f"{make_safe_name(name)}_{now:%Y%m%d_%H%M%S}_{project_id}"
        project_dir = PROJECTS_DIR / folder_name
        project_dir.mkdir(parents=True, exist_ok=True)

        project = cls(
            id=project_id,
            name=name,
            project_dir=str(project_dir),
            created_at=now.isoformat(timespec="seconds"),
            updated_at=now.isoformat(timespec="seconds"),
            metadata={},
        )
        project.save()
        return project

    @property
    def metadata_path(self) -> Path:
        return Path(self.project_dir) / "project.json"

    def save(self) -> None:
        self.updated_at = datetime.now().isoformat(timespec="seconds")
        serialized = json.dumps(asdict(self), ensure_ascii=False, indent=2)
        temporary_path = self.metadata_path.with_name(f".{self.metadata_path.name}.tmp")
        temporary_path.write_text(serialized, encoding="utf-8")
        temporary_path.replace(self.metadata_path)

    @classmethod
    def load(cls, metadata_path: Path) -> WorkspaceProject:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        return cls(**data)


VideoProject = WorkspaceProject


def load_all_projects() -> list[WorkspaceProject]:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    projects: list[WorkspaceProject] = []
    for metadata_path in PROJECTS_DIR.glob("*/project.json"):
        try:
            projects.append(WorkspaceProject.load(metadata_path))
        except Exception:
            continue
    return sorted(projects, key=lambda p: p.updated_at, reverse=True)


def delete_project(project: WorkspaceProject) -> None:
    projects_root = PROJECTS_DIR.resolve()
    project_dir = Path(project.project_dir).resolve()
    if not project_dir.exists():
        return
    if not project_dir.is_relative_to(projects_root) or project_dir == projects_root:
        raise ValueError("Invalid project directory.")
    shutil.rmtree(project_dir)
