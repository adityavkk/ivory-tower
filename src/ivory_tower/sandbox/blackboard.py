"""Orchestrator-mediated blackboard for shared agent state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import SharedVolume


@dataclass
class FileBlackboard:
    """Orchestrator-mediated file-based blackboard.
    
    Agents never write directly to the blackboard. The orchestrator
    reads agent output from their private workspace and appends it
    to the shared volume via this class.
    """
    volume: SharedVolume
    file_name: str | None        # Single file (transcript mode)
    access_mode: str             # "read", "append", "rw"

    def get_content(self) -> str:
        """Read current blackboard content."""
        if self.file_name:
            try:
                return self.volume.read_file(self.file_name)
            except (FileNotFoundError, OSError):
                return ""
        # Directory mode: concatenate all files
        files = sorted(self.volume.list_files())
        if not files:
            return ""
        parts = []
        for f in files:
            try:
                parts.append(self.volume.read_file(f))
            except (FileNotFoundError, OSError):
                continue
        return "\n\n---\n\n".join(parts)

    def append(self, agent_name: str, round_num: int, content: str) -> None:
        """Orchestrator appends agent's contribution to the blackboard.

        This is the ONLY write path. Agents never write directly.
        
        Raises:
            PermissionError: If blackboard is read-only in this phase.
        """
        if self.access_mode == "read":
            raise PermissionError("Blackboard is read-only in this phase")

        if self.file_name:
            # Transcript mode: append to single file
            header = f"\n\n## {agent_name} -- Round {round_num}\n\n"
            self.volume.append_file(self.file_name, header + content)
        else:
            # Directory mode: write a new file
            fname = f"{round_num:02d}-{agent_name}.md"
            self.volume.write_file(fname, content)

    def snapshot(self, label: str) -> str:
        """Return current content for archival."""
        return self.get_content()
