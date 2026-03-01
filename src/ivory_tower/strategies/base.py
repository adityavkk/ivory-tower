"""Base protocol for research strategies."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ivory_tower.models import Manifest


@runtime_checkable
class ResearchStrategy(Protocol):
    """Protocol that all research strategies must implement."""

    name: str
    description: str

    def validate(self, config: Any) -> list[str]:
        """Validate config and return list of error messages (empty = valid)."""
        ...

    def create_manifest(self, config: Any, run_id: str) -> Manifest:
        """Create the initial manifest for this strategy."""
        ...

    def run(self, run_dir: Path, config: Any, manifest: Manifest) -> Manifest:
        """Execute the full strategy pipeline."""
        ...

    def resume(self, run_dir: Path, config: Any, manifest: Manifest) -> Manifest:
        """Resume a partially-completed run."""
        ...

    def dry_run(self, config: Any) -> None:
        """Print the execution plan without running anything."""
        ...

    def format_status(self, manifest: Manifest) -> list[tuple[str, str]]:
        """Return list of (label, status_value) for display."""
        ...

    def phases_to_dict(self, phases: dict) -> dict:
        """Serialize strategy-specific phases to dict."""
        ...

    def phases_from_dict(self, data: dict) -> dict:
        """Deserialize strategy-specific phases from dict."""
        ...
