"""Orchestrator-mediated blackboard for shared agent state."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import SharedVolume

logger = logging.getLogger(__name__)


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
                content = self.volume.read_file(self.file_name)
                logger.debug("Blackboard read: file=%s (%d chars)", self.file_name, len(content))
                return content
            except (FileNotFoundError, OSError):
                logger.debug("Blackboard read: file=%s (not found, returning empty)", self.file_name)
                return ""
        # Directory mode: concatenate all files
        files = sorted(self.volume.list_files())
        if not files:
            logger.debug("Blackboard read: directory mode (empty)")
            return ""
        parts = []
        for f in files:
            try:
                parts.append(self.volume.read_file(f))
            except (FileNotFoundError, OSError):
                continue
        content = "\n\n---\n\n".join(parts)
        logger.debug("Blackboard read: directory mode (%d files, %d chars)", len(parts), len(content))
        return content

    def append(self, agent_name: str, round_num: int, content: str) -> None:
        """Orchestrator appends agent's contribution to the blackboard.

        This is the ONLY write path. Agents never write directly.
        
        Raises:
            PermissionError: If blackboard is read-only in this phase.
        """
        if self.access_mode == "read":
            logger.warning("Blackboard write rejected: read-only (agent=%s round=%d)", agent_name, round_num)
            raise PermissionError("Blackboard is read-only in this phase")

        if self.file_name:
            # Transcript mode: append to single file
            header = f"\n\n## {agent_name} -- Round {round_num}\n\n"
            self.volume.append_file(self.file_name, header + content)
            logger.debug("Blackboard append: agent=%s round=%d file=%s (%d chars)", agent_name, round_num, self.file_name, len(content))
        else:
            # Directory mode: write a new file
            fname = f"{round_num:02d}-{agent_name}.md"
            self.volume.write_file(fname, content)
            logger.debug("Blackboard write: agent=%s round=%d file=%s (%d chars)", agent_name, round_num, fname, len(content))

    def snapshot(self, label: str) -> str:
        """Return current content for archival."""
        content = self.get_content()
        logger.debug("Blackboard snapshot: label=%s (%d chars)", label, len(content))
        return content
