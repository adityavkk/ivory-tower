"""Council strategy: the original 3-phase multi-agent research pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ivory_tower.models import Manifest


class CouncilStrategy:
    """Multi-agent research via independent research, cross-pollination, and synthesis."""

    name: str = "council"
    description: str = "Multi-agent research with cross-pollination and synthesis"

    def validate(self, config: Any) -> list[str]:
        raise NotImplementedError

    def create_manifest(self, config: Any, run_id: str) -> Manifest:
        raise NotImplementedError

    def run(self, run_dir: Path, config: Any, manifest: Manifest) -> Manifest:
        raise NotImplementedError

    def resume(self, run_dir: Path, config: Any, manifest: Manifest) -> Manifest:
        raise NotImplementedError

    def dry_run(self, config: Any) -> None:
        raise NotImplementedError

    def format_status(self, manifest: Manifest) -> list[tuple[str, str]]:
        raise NotImplementedError

    def phases_to_dict(self, phases: dict) -> dict:
        raise NotImplementedError

    def phases_from_dict(self, data: dict) -> dict:
        raise NotImplementedError
