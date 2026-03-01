"""Tests for ivory_tower.run -- run ID generation and directory setup."""

import re
from pathlib import Path

from ivory_tower.models import (
    CrossPollinationPhase,
    Flags,
    Manifest,
    PhaseStatus,
    ResearchPhase,
    SynthesisPhase,
)
from ivory_tower.run import (
    create_initial_manifest,
    create_run_directory,
    generate_run_id,
)


# --- generate_run_id ---

RUN_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")


class TestGenerateRunId:
    def test_format_matches_regex(self):
        rid = generate_run_id()
        assert RUN_ID_RE.match(rid), f"Run ID {rid!r} doesn't match expected format"

    def test_uniqueness(self):
        ids = {generate_run_id() for _ in range(20)}
        # With 6 hex chars of randomness, collisions in 20 samples are near impossible
        assert len(ids) == 20

    def test_date_portion_is_plausible(self):
        rid = generate_run_id()
        year = int(rid[:4])
        month = int(rid[4:6])
        day = int(rid[6:8])
        assert 2025 <= year <= 2030
        assert 1 <= month <= 12
        assert 1 <= day <= 31


# --- create_run_directory ---


class TestCreateRunDirectory:
    def test_creates_expected_dirs(self, tmp_path: Path):
        run_dir = create_run_directory(tmp_path, "20260301-143000-a1b2c3")
        assert run_dir == tmp_path / "20260301-143000-a1b2c3"
        assert run_dir.is_dir()
        assert (run_dir / "phase1").is_dir()
        assert (run_dir / "phase2").is_dir()
        assert (run_dir / "phase3").is_dir()
        assert (run_dir / "logs").is_dir()

    def test_returns_run_dir_path(self, tmp_path: Path):
        run_dir = create_run_directory(tmp_path, "my-run")
        assert run_dir.name == "my-run"
        assert run_dir.parent == tmp_path

    def test_idempotent(self, tmp_path: Path):
        """Calling twice doesn't raise."""
        create_run_directory(tmp_path, "run1")
        create_run_directory(tmp_path, "run1")  # no error
        assert (tmp_path / "run1" / "phase1").is_dir()


# --- create_initial_manifest ---


class TestCreateInitialManifest:
    def test_all_phases_pending(self):
        m = create_initial_manifest(
            run_id="20260301-143000-a1b2c3",
            topic="AI safety",
            agents=["claude-opus", "codex-5.3-xhigh"],
            synthesizer="claude-opus",
            flags=Flags(raw=False, instructions=None, verbose=True),
        )
        assert isinstance(m, Manifest)
        assert m.run_id == "20260301-143000-a1b2c3"
        assert m.topic == "AI safety"
        assert m.agents == ["claude-opus", "codex-5.3-xhigh"]
        assert m.synthesizer == "claude-opus"

        # Research phase
        rp = m.phases["research"]
        assert isinstance(rp, ResearchPhase)
        assert rp.status is PhaseStatus.PENDING
        assert rp.started_at is None
        assert rp.completed_at is None
        assert rp.duration_seconds is None
        # Pre-populated agent results in pending state
        assert "claude-opus" in rp.agents
        assert "codex-5.3-xhigh" in rp.agents
        assert rp.agents["claude-opus"].status is PhaseStatus.PENDING
        assert rp.agents["claude-opus"].output == "phase1/claude-opus-report.md"

        # Cross-pollination phase
        cp = m.phases["cross_pollination"]
        assert isinstance(cp, CrossPollinationPhase)
        assert cp.status is PhaseStatus.PENDING
        # Sessions pre-populated for all N*(N-1) pairs
        assert len(cp.sessions) == 2  # 2 agents => 2*(2-1)=2 sessions
        assert "claude-opus-cross-codex-5.3-xhigh" in cp.sessions
        assert "codex-5.3-xhigh-cross-claude-opus" in cp.sessions
        sess = cp.sessions["claude-opus-cross-codex-5.3-xhigh"]
        assert sess.status is PhaseStatus.PENDING
        assert sess.output == "phase2/claude-opus-cross-codex-5.3-xhigh.md"

        # Synthesis phase
        sp = m.phases["synthesis"]
        assert isinstance(sp, SynthesisPhase)
        assert sp.status is PhaseStatus.PENDING
        assert sp.agent == "claude-opus"
        assert sp.output == "phase3/final-report.md"

        # Flags
        assert m.flags.verbose is True
        assert m.flags.raw is False

        # Total duration
        assert m.total_duration_seconds is None

    def test_three_agents_session_count(self):
        m = create_initial_manifest(
            run_id="run-3",
            topic="t",
            agents=["a", "b", "c"],
            synthesizer="a",
            flags=Flags(),
        )
        cp = m.phases["cross_pollination"]
        assert isinstance(cp, CrossPollinationPhase)
        # 3 agents => 3*2 = 6 sessions
        assert len(cp.sessions) == 6
        expected_keys = {
            "a-cross-b", "a-cross-c",
            "b-cross-a", "b-cross-c",
            "c-cross-a", "c-cross-b",
        }
        assert set(cp.sessions.keys()) == expected_keys
