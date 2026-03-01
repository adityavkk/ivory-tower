"""Tests for FileBlackboard using real LocalSharedVolume backed by tmp_path."""

from __future__ import annotations

import pytest
from pathlib import Path

from ivory_tower.sandbox.blackboard import FileBlackboard
from ivory_tower.sandbox.local import LocalSharedVolume


@pytest.fixture
def shared_volume(tmp_path: Path) -> LocalSharedVolume:
    """Create a real LocalSharedVolume backed by tmp_path."""
    return LocalSharedVolume(id="test-vol", path=tmp_path)


# --- Transcript mode tests ---


class TestTranscriptMode:
    """Tests for single-file transcript mode (file_name is set)."""

    def test_empty_initially(self, shared_volume: LocalSharedVolume) -> None:
        """get_content() returns empty string when no content exists."""
        bb = FileBlackboard(
            volume=shared_volume,
            file_name="transcript.md",
            access_mode="append",
        )
        assert bb.get_content() == ""

    def test_append_single_agent(self, shared_volume: LocalSharedVolume) -> None:
        """Appending from one agent creates content with proper header."""
        bb = FileBlackboard(
            volume=shared_volume,
            file_name="transcript.md",
            access_mode="append",
        )
        bb.append("analyst", 1, "Market is bearish.")
        content = bb.get_content()
        assert "## analyst -- Round 1" in content
        assert "Market is bearish." in content

    def test_append_two_agents_two_rounds(
        self, shared_volume: LocalSharedVolume
    ) -> None:
        """Append from 2 agents across 2 rounds, verify full transcript."""
        bb = FileBlackboard(
            volume=shared_volume,
            file_name="transcript.md",
            access_mode="append",
        )
        bb.append("alice", 1, "Alice round 1 contribution.")
        bb.append("bob", 1, "Bob round 1 contribution.")
        bb.append("alice", 2, "Alice round 2 contribution.")
        bb.append("bob", 2, "Bob round 2 contribution.")

        content = bb.get_content()
        assert "## alice -- Round 1" in content
        assert "## bob -- Round 1" in content
        assert "## alice -- Round 2" in content
        assert "## bob -- Round 2" in content
        assert "Alice round 1 contribution." in content
        assert "Bob round 2 contribution." in content

    def test_content_header_format(self, shared_volume: LocalSharedVolume) -> None:
        """Verify headers follow ## agent_name -- Round N format."""
        bb = FileBlackboard(
            volume=shared_volume,
            file_name="transcript.md",
            access_mode="append",
        )
        bb.append("my_agent", 3, "Some text.")
        content = bb.get_content()
        assert "## my_agent -- Round 3" in content

    def test_multiple_rounds_grow_transcript(
        self, shared_volume: LocalSharedVolume
    ) -> None:
        """Appending 3 rounds of content, transcript grows correctly."""
        bb = FileBlackboard(
            volume=shared_volume,
            file_name="transcript.md",
            access_mode="append",
        )
        bb.append("agent1", 1, "Round 1 text.")
        content_after_1 = bb.get_content()

        bb.append("agent1", 2, "Round 2 text.")
        content_after_2 = bb.get_content()

        bb.append("agent1", 3, "Round 3 text.")
        content_after_3 = bb.get_content()

        # Each round adds more content
        assert len(content_after_2) > len(content_after_1)
        assert len(content_after_3) > len(content_after_2)

        # All rounds present in final content
        assert "## agent1 -- Round 1" in content_after_3
        assert "## agent1 -- Round 2" in content_after_3
        assert "## agent1 -- Round 3" in content_after_3
        assert "Round 1 text." in content_after_3
        assert "Round 2 text." in content_after_3
        assert "Round 3 text." in content_after_3


# --- Directory mode tests ---


class TestDirectoryMode:
    """Tests for directory mode (file_name is None)."""

    def test_empty_initially(self, shared_volume: LocalSharedVolume) -> None:
        """get_content() returns empty string when directory has no files."""
        bb = FileBlackboard(
            volume=shared_volume,
            file_name=None,
            access_mode="append",
        )
        assert bb.get_content() == ""

    def test_append_creates_files(self, shared_volume: LocalSharedVolume) -> None:
        """Appending in directory mode creates properly named files."""
        bb = FileBlackboard(
            volume=shared_volume,
            file_name=None,
            access_mode="append",
        )
        bb.append("agent1", 1, "Agent 1 output.")
        bb.append("agent2", 1, "Agent 2 output.")

        files = sorted(shared_volume.list_files())
        assert "01-agent1.md" in files
        assert "01-agent2.md" in files

    def test_get_content_concatenates_sorted(
        self, shared_volume: LocalSharedVolume
    ) -> None:
        """get_content() concatenates files with --- separator, sorted alphabetically."""
        bb = FileBlackboard(
            volume=shared_volume,
            file_name=None,
            access_mode="append",
        )
        bb.append("beta", 1, "Beta output.")
        bb.append("alpha", 1, "Alpha output.")

        content = bb.get_content()
        # Sorted: 01-alpha.md comes before 01-beta.md
        alpha_pos = content.index("Alpha output.")
        beta_pos = content.index("Beta output.")
        assert alpha_pos < beta_pos
        assert "\n\n---\n\n" in content

    def test_populated_directory_all_files_read(
        self, shared_volume: LocalSharedVolume
    ) -> None:
        """All files in populated directory are read and concatenated."""
        # Pre-populate the volume directly
        shared_volume.write_file("01-analyst.md", "Analysis complete.")
        shared_volume.write_file("02-critic.md", "Critique follows.")
        shared_volume.write_file("03-synthesizer.md", "Synthesis done.")

        bb = FileBlackboard(
            volume=shared_volume,
            file_name=None,
            access_mode="append",
        )
        content = bb.get_content()
        assert "Analysis complete." in content
        assert "Critique follows." in content
        assert "Synthesis done." in content
        # 3 files means 2 separators
        assert content.count("\n\n---\n\n") == 2


# --- Access mode tests ---


class TestAccessModes:
    """Tests for read, append, and rw access modes."""

    def test_read_only_append_raises(self, shared_volume: LocalSharedVolume) -> None:
        """append() raises PermissionError when access_mode is 'read'."""
        bb = FileBlackboard(
            volume=shared_volume,
            file_name="transcript.md",
            access_mode="read",
        )
        with pytest.raises(PermissionError, match="read-only"):
            bb.append("agent", 1, "Should fail.")

    def test_read_only_get_content_works(
        self, shared_volume: LocalSharedVolume
    ) -> None:
        """get_content() works even in read-only mode."""
        # Pre-populate
        shared_volume.write_file("transcript.md", "Existing content.")

        bb = FileBlackboard(
            volume=shared_volume,
            file_name="transcript.md",
            access_mode="read",
        )
        assert bb.get_content() == "Existing content."

    def test_append_mode_works(self, shared_volume: LocalSharedVolume) -> None:
        """append() succeeds when access_mode is 'append'."""
        bb = FileBlackboard(
            volume=shared_volume,
            file_name="transcript.md",
            access_mode="append",
        )
        bb.append("agent", 1, "Content.")
        assert "Content." in bb.get_content()

    def test_rw_mode_append_works(self, shared_volume: LocalSharedVolume) -> None:
        """append() succeeds when access_mode is 'rw'."""
        bb = FileBlackboard(
            volume=shared_volume,
            file_name="transcript.md",
            access_mode="rw",
        )
        bb.append("agent", 1, "RW content.")
        assert "RW content." in bb.get_content()


# --- Snapshot tests ---


class TestSnapshot:
    """Tests for the snapshot method."""

    def test_snapshot_returns_current_content(
        self, shared_volume: LocalSharedVolume
    ) -> None:
        """snapshot() returns current content string."""
        bb = FileBlackboard(
            volume=shared_volume,
            file_name="transcript.md",
            access_mode="append",
        )
        bb.append("agent", 1, "Snapshot test.")
        snap = bb.snapshot("phase-1")
        assert "Snapshot test." in snap
        assert "## agent -- Round 1" in snap

    def test_snapshot_empty_blackboard(
        self, shared_volume: LocalSharedVolume
    ) -> None:
        """snapshot() returns empty string on empty blackboard."""
        bb = FileBlackboard(
            volume=shared_volume,
            file_name="transcript.md",
            access_mode="append",
        )
        assert bb.snapshot("empty") == ""

    def test_snapshot_directory_mode(
        self, shared_volume: LocalSharedVolume
    ) -> None:
        """snapshot() works in directory mode too."""
        bb = FileBlackboard(
            volume=shared_volume,
            file_name=None,
            access_mode="append",
        )
        bb.append("a", 1, "File A.")
        bb.append("b", 1, "File B.")
        snap = bb.snapshot("dir-snap")
        assert "File A." in snap
        assert "File B." in snap
