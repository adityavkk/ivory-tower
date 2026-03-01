"""Tests for template executor: isolation modes and GenericTemplateExecutor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ivory_tower.executor.types import AgentOutput
from ivory_tower.sandbox.local import (
    LocalSandbox,
    LocalSandboxProvider,
    LocalSharedVolume,
)
from ivory_tower.sandbox.types import SandboxConfig
from ivory_tower.templates.executor import (
    GenericTemplateExecutor,
    setup_phase_isolation,
)
from ivory_tower.templates.loader import (
    BlackboardConfig,
    PhaseConfig,
    StrategyDefaults,
    StrategyTemplate,
)


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


class MockExecutor:
    """Mock agent executor that writes a report into the sandbox."""

    name = "mock"

    def run(
        self,
        sandbox,
        agent_name: str,
        prompt: str,
        output_dir: str,
        model: str | None = None,
        system_prompt: str | None = None,
        verbose: bool = False,
    ) -> AgentOutput:
        report_path = f"{output_dir}/{agent_name}-report.md"
        sandbox.write_file(report_path, f"Report from {agent_name}")
        return AgentOutput(
            report_path=report_path,
            raw_output=f"Report from {agent_name}",
            duration_seconds=0.1,
        )


@pytest.fixture
def provider() -> LocalSandboxProvider:
    return LocalSandboxProvider()


@pytest.fixture
def config() -> SandboxConfig:
    return SandboxConfig(backend="local")


def _make_sandbox(tmp_path: Path, agent_name: str) -> LocalSandbox:
    workspace = tmp_path / "sandboxes" / agent_name / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return LocalSandbox(id=f"test-{agent_name}", agent_name=agent_name, workspace_dir=workspace)


def _make_volume(tmp_path: Path, name: str) -> LocalSharedVolume:
    vol_dir = tmp_path / "volumes" / name
    vol_dir.mkdir(parents=True, exist_ok=True)
    return LocalSharedVolume(id=f"test-{name}", path=vol_dir)


def _make_phase(
    name: str = "test-phase",
    isolation: str = "full",
    agents: str | list[str] = "all",
    output: str = "{agent}-output.md",
    rounds: int | None = None,
    input_from: str | list[str] | None = None,
    blackboard: BlackboardConfig | None = None,
    fan_out: str | None = None,
) -> PhaseConfig:
    return PhaseConfig(
        name=name,
        description=f"Test phase: {name}",
        isolation=isolation,
        agents=agents,
        output=output,
        rounds=rounds,
        input_from=input_from,
        blackboard=blackboard,
        fan_out=fan_out,
    )


def _make_template(
    phases: list[PhaseConfig],
    name: str = "test-strategy",
    defaults_rounds: int | None = None,
) -> StrategyTemplate:
    return StrategyTemplate(
        name=name,
        description="Test strategy",
        version=1,
        phases=phases,
        defaults=StrategyDefaults(rounds=defaults_rounds),
    )


# ---------------------------------------------------------------------------
# Commit 10: Isolation mode tests
# ---------------------------------------------------------------------------


class TestIsolationFull:
    """setup_phase_isolation('full', ...) -- sandboxes receive no peer data."""

    def test_full_isolation_no_data_copied(self, tmp_path: Path) -> None:
        """Full isolation: sandboxes start empty, no peer data injected."""
        alice = _make_sandbox(tmp_path, "alice")
        bob = _make_sandbox(tmp_path, "bob")
        sandboxes = {"alice": alice, "bob": bob}

        phase = _make_phase(isolation="full")

        # Even if there are previous outputs, nothing gets copied
        prev = {"prev-phase": {"alice": tmp_path / "dummy.md"}}

        setup_phase_isolation(phase, sandboxes, {}, prev)

        assert alice.list_files() == []
        assert bob.list_files() == []


class TestIsolationReadPeers:
    """setup_phase_isolation('read-peers', ...) -- each sandbox gets peer outputs."""

    def test_read_peers_copies_peer_outputs(self, tmp_path: Path) -> None:
        alice = _make_sandbox(tmp_path, "alice")
        bob = _make_sandbox(tmp_path, "bob")
        sandboxes = {"alice": alice, "bob": bob}

        # Create previous outputs on disk
        prev_dir = tmp_path / "prev"
        prev_dir.mkdir()
        alice_output = prev_dir / "alice-opening.md"
        alice_output.write_text("Alice's opening")
        bob_output = prev_dir / "bob-opening.md"
        bob_output.write_text("Bob's opening")

        previous_outputs = {
            "opening": {"alice": alice_output, "bob": bob_output}
        }

        phase = _make_phase(isolation="read-peers", input_from="opening")

        setup_phase_isolation(phase, sandboxes, {}, previous_outputs)

        # Alice should see Bob's output but NOT her own
        assert alice.file_exists("peers/bob.md")
        assert alice.read_file("peers/bob.md") == "Bob's opening"
        assert not alice.file_exists("peers/alice.md")

        # Bob should see Alice's output but NOT his own
        assert bob.file_exists("peers/alice.md")
        assert bob.read_file("peers/alice.md") == "Alice's opening"
        assert not bob.file_exists("peers/bob.md")

    def test_read_peers_no_input_from_is_noop(self, tmp_path: Path) -> None:
        alice = _make_sandbox(tmp_path, "alice")
        phase = _make_phase(isolation="read-peers", input_from=None)

        setup_phase_isolation(phase, {"alice": alice}, {}, {})
        assert alice.list_files() == []

    def test_read_peers_list_input_from_uses_first(self, tmp_path: Path) -> None:
        alice = _make_sandbox(tmp_path, "alice")
        bob = _make_sandbox(tmp_path, "bob")

        prev_dir = tmp_path / "prev"
        prev_dir.mkdir()
        bob_output = prev_dir / "bob.md"
        bob_output.write_text("Bob phase1")

        previous_outputs = {"phase1": {"bob": bob_output}}
        phase = _make_phase(isolation="read-peers", input_from=["phase1", "phase2"])

        setup_phase_isolation(phase, {"alice": alice, "bob": bob}, {}, previous_outputs)
        assert alice.file_exists("peers/bob.md")


class TestIsolationReadAll:
    """setup_phase_isolation('read-all', ...) -- sandboxes get all outputs from specified phases."""

    def test_read_all_copies_all_phase_outputs(self, tmp_path: Path) -> None:
        alice = _make_sandbox(tmp_path, "alice")
        sandboxes = {"alice": alice}

        prev_dir = tmp_path / "prev"
        prev_dir.mkdir()
        a_out = prev_dir / "a.md"
        a_out.write_text("A output")
        b_out = prev_dir / "b.md"
        b_out.write_text("B output")
        c_out = prev_dir / "c.md"
        c_out.write_text("C output")

        previous_outputs = {
            "opening": {"agent-a": a_out},
            "rounds": {"agent-b": b_out},
            "closing": {"agent-c": c_out},
        }

        phase = _make_phase(
            isolation="read-all",
            input_from=["opening", "rounds", "closing"],
        )

        setup_phase_isolation(phase, sandboxes, {}, previous_outputs)

        assert alice.read_file("inputs/opening/agent-a.md") == "A output"
        assert alice.read_file("inputs/rounds/agent-b.md") == "B output"
        assert alice.read_file("inputs/closing/agent-c.md") == "C output"

    def test_read_all_string_input_from(self, tmp_path: Path) -> None:
        alice = _make_sandbox(tmp_path, "alice")
        prev_dir = tmp_path / "prev"
        prev_dir.mkdir()
        a_out = prev_dir / "a.md"
        a_out.write_text("single phase")

        previous_outputs = {"phase1": {"agent-a": a_out}}
        phase = _make_phase(isolation="read-all", input_from="phase1")

        setup_phase_isolation(phase, {"alice": alice}, {}, previous_outputs)
        assert alice.read_file("inputs/phase1/agent-a.md") == "single phase"

    def test_read_all_no_input_from_is_noop(self, tmp_path: Path) -> None:
        alice = _make_sandbox(tmp_path, "alice")
        phase = _make_phase(isolation="read-all", input_from=None)

        setup_phase_isolation(phase, {"alice": alice}, {}, {})
        assert alice.list_files() == []


class TestIsolationBlackboard:
    """setup_phase_isolation('blackboard', ...) -- sandboxes get current blackboard content."""

    def test_blackboard_content_copied_to_sandboxes(self, tmp_path: Path) -> None:
        alice = _make_sandbox(tmp_path, "alice")
        bob = _make_sandbox(tmp_path, "bob")

        volume = _make_volume(tmp_path, "transcript")
        volume.write_file("debate.md", "Previous debate content")

        bb_config = BlackboardConfig(
            name="transcript",
            file="debate.md",
            access="append",
        )
        phase = _make_phase(isolation="blackboard", blackboard=bb_config)

        setup_phase_isolation(
            phase,
            {"alice": alice, "bob": bob},
            {"transcript": volume},
            {},
        )

        assert alice.read_file("blackboard/debate.md") == "Previous debate content"
        assert bob.read_file("blackboard/debate.md") == "Previous debate content"

    def test_blackboard_missing_file_gives_empty(self, tmp_path: Path) -> None:
        alice = _make_sandbox(tmp_path, "alice")
        volume = _make_volume(tmp_path, "transcript")
        # Don't write the file -- it doesn't exist

        bb_config = BlackboardConfig(name="transcript", file="missing.md", access="append")
        phase = _make_phase(isolation="blackboard", blackboard=bb_config)

        setup_phase_isolation(
            phase,
            {"alice": alice},
            {"transcript": volume},
            {},
        )

        assert alice.read_file("blackboard/missing.md") == ""

    def test_blackboard_no_volume_is_noop(self, tmp_path: Path) -> None:
        alice = _make_sandbox(tmp_path, "alice")
        bb_config = BlackboardConfig(name="nonexistent", file="x.md", access="append")
        phase = _make_phase(isolation="blackboard", blackboard=bb_config)

        setup_phase_isolation(phase, {"alice": alice}, {}, {})
        assert alice.list_files() == []


class TestIsolationReadBlackboard:
    """setup_phase_isolation('read-blackboard', ...) -- sandboxes get read-only blackboard."""

    def test_read_blackboard_copies_content(self, tmp_path: Path) -> None:
        alice = _make_sandbox(tmp_path, "alice")
        volume = _make_volume(tmp_path, "transcript")
        volume.write_file("transcript.md", "Full transcript here")

        bb_config = BlackboardConfig(name="transcript", file="transcript.md", access="read")
        phase = _make_phase(isolation="read-blackboard", blackboard=bb_config)

        setup_phase_isolation(
            phase,
            {"alice": alice},
            {"transcript": volume},
            {},
        )

        assert alice.read_file("blackboard/transcript.md") == "Full transcript here"

    def test_read_blackboard_missing_file_gives_empty(self, tmp_path: Path) -> None:
        alice = _make_sandbox(tmp_path, "alice")
        volume = _make_volume(tmp_path, "transcript")

        bb_config = BlackboardConfig(name="transcript", file="nope.md", access="read")
        phase = _make_phase(isolation="read-blackboard", blackboard=bb_config)

        setup_phase_isolation(
            phase,
            {"alice": alice},
            {"transcript": volume},
            {},
        )

        assert alice.read_file("blackboard/nope.md") == ""


class TestIsolationTeam:
    """setup_phase_isolation('team', ...) -- team members get team blackboard."""

    def test_team_isolation_copies_team_files(self, tmp_path: Path) -> None:
        alice = _make_sandbox(tmp_path, "alice")
        bob = _make_sandbox(tmp_path, "bob")

        team_vol = _make_volume(tmp_path, "team-blue")
        team_vol.write_file("research.md", "Blue team research")

        teams = {"alice": "blue", "bob": "red"}
        bb_config = BlackboardConfig(name="blue-board", file=None, access="rw")
        phase = _make_phase(isolation="team", blackboard=bb_config)

        setup_phase_isolation(
            phase,
            {"alice": alice, "bob": bob},
            {"team-blue": team_vol, "team-red": _make_volume(tmp_path, "team-red")},
            {},
            teams=teams,
        )

        # Alice (blue team) should have team files
        assert alice.file_exists("team-board/research.md")
        assert alice.read_file("team-board/research.md") == "Blue team research"

    def test_team_isolation_no_teams_is_noop(self, tmp_path: Path) -> None:
        alice = _make_sandbox(tmp_path, "alice")
        bb_config = BlackboardConfig(name="board", file=None, access="rw")
        phase = _make_phase(isolation="team", blackboard=bb_config)

        setup_phase_isolation(phase, {"alice": alice}, {}, {}, teams=None)
        assert alice.list_files() == []

    def test_team_isolation_no_blackboard_is_noop(self, tmp_path: Path) -> None:
        alice = _make_sandbox(tmp_path, "alice")
        phase = _make_phase(isolation="team")
        teams = {"alice": "blue"}

        setup_phase_isolation(phase, {"alice": alice}, {}, {}, teams=teams)
        assert alice.list_files() == []


class TestIsolationCrossTeamRead:
    """setup_phase_isolation('cross-team-read', ...) -- agents get opposing team outputs."""

    def test_cross_team_read_copies_opposing_team(self, tmp_path: Path) -> None:
        alice = _make_sandbox(tmp_path, "alice")
        bob = _make_sandbox(tmp_path, "bob")

        prev_dir = tmp_path / "prev"
        prev_dir.mkdir()
        alice_out = prev_dir / "alice.md"
        alice_out.write_text("Alice (blue) research")
        bob_out = prev_dir / "bob.md"
        bob_out.write_text("Bob (red) critique")

        previous_outputs = {
            "research": {"alice": alice_out, "bob": bob_out},
        }
        teams = {"alice": "blue", "bob": "red"}
        phase = _make_phase(isolation="cross-team-read", input_from="research")

        setup_phase_isolation(
            phase,
            {"alice": alice, "bob": bob},
            {},
            previous_outputs,
            teams=teams,
        )

        # Alice (blue) sees Bob (red) in opposing/
        assert alice.file_exists("opposing/bob.md")
        assert alice.read_file("opposing/bob.md") == "Bob (red) critique"
        # Alice should NOT see her own output
        assert not alice.file_exists("opposing/alice.md")

        # Bob (red) sees Alice (blue) in opposing/
        assert bob.file_exists("opposing/alice.md")
        assert not bob.file_exists("opposing/bob.md")

    def test_cross_team_read_no_teams_is_noop(self, tmp_path: Path) -> None:
        alice = _make_sandbox(tmp_path, "alice")
        prev_dir = tmp_path / "prev"
        prev_dir.mkdir()
        alice_out = prev_dir / "alice.md"
        alice_out.write_text("output")

        previous_outputs = {"research": {"alice": alice_out}}
        phase = _make_phase(isolation="cross-team-read", input_from="research")

        setup_phase_isolation(phase, {"alice": alice}, {}, previous_outputs, teams=None)
        assert alice.list_files() == []

    def test_cross_team_read_list_input_from_uses_first(self, tmp_path: Path) -> None:
        alice = _make_sandbox(tmp_path, "alice")
        bob = _make_sandbox(tmp_path, "bob")

        prev_dir = tmp_path / "prev"
        prev_dir.mkdir()
        bob_out = prev_dir / "bob.md"
        bob_out.write_text("Bob phase1")

        previous_outputs = {"phase1": {"bob": bob_out}}
        teams = {"alice": "blue", "bob": "red"}
        phase = _make_phase(isolation="cross-team-read", input_from=["phase1", "phase2"])

        setup_phase_isolation(
            phase, {"alice": alice, "bob": bob}, {}, previous_outputs, teams=teams
        )
        assert alice.file_exists("opposing/bob.md")


class TestIsolationNone:
    """setup_phase_isolation('none', ...) -- no-op."""

    def test_none_isolation_is_noop(self, tmp_path: Path) -> None:
        alice = _make_sandbox(tmp_path, "alice")
        phase = _make_phase(isolation="none")

        setup_phase_isolation(phase, {"alice": alice}, {}, {})
        assert alice.list_files() == []


# ---------------------------------------------------------------------------
# Commit 11: GenericTemplateExecutor tests
# ---------------------------------------------------------------------------


class TestGenericTemplateExecutorDebateTemplate:
    """Load debate template, run with mock executor -- all 4 phases execute in order."""

    def test_debate_template_all_phases_execute(self, tmp_path: Path) -> None:
        """Debate template produces outputs for all 4 phases: opening, rounds, closing, verdict."""
        # Build a debate-like template programmatically
        phases = [
            _make_phase(
                name="opening",
                isolation="full",
                agents="all",
                output="{agent}-opening.md",
            ),
            _make_phase(
                name="rounds",
                isolation="blackboard",
                agents="all",
                output="{agent}-round-{round}.md",
                rounds=2,
                blackboard=BlackboardConfig(
                    name="transcript",
                    file="debate-transcript.md",
                    access="append",
                ),
            ),
            _make_phase(
                name="closing",
                isolation="read-blackboard",
                agents="all",
                output="{agent}-closing.md",
                blackboard=BlackboardConfig(
                    name="transcript",
                    file="debate-transcript.md",
                    access="read",
                ),
            ),
            _make_phase(
                name="verdict",
                isolation="read-all",
                agents=["synthesizer"],
                output="verdict.md",
                input_from=["opening", "rounds", "closing"],
            ),
        ]
        template = _make_template(phases)
        run_dir = tmp_path / "run-001"
        run_dir.mkdir()

        mock_executor = MockExecutor()

        with patch("ivory_tower.templates.executor.get_provider") as mock_get_provider, \
             patch("ivory_tower.templates.executor.get_executor") as mock_get_executor:
            mock_get_provider.return_value = LocalSandboxProvider()
            mock_get_executor.return_value = mock_executor

            executor = GenericTemplateExecutor(template)
            outputs = executor.run(
                run_dir=run_dir,
                agents=["alice", "bob"],
                synthesizer="judge",
                sandbox_backend="local",
                executor_name="mock",
                topic="AI safety",
            )

        # All 4 phases present
        assert "opening" in outputs
        assert "rounds" in outputs
        assert "closing" in outputs
        assert "verdict" in outputs


class TestSinglePhaseExecution:
    """Single phase: creates sandboxes, runs agents, copies outputs to canonical paths."""

    def test_single_phase_canonical_output_paths(self, tmp_path: Path) -> None:
        phases = [
            _make_phase(
                name="analysis",
                isolation="full",
                agents="all",
                output="{agent}-analysis.md",
            ),
        ]
        template = _make_template(phases)
        run_dir = tmp_path / "run-002"
        run_dir.mkdir()

        mock_executor = MockExecutor()

        with patch("ivory_tower.templates.executor.get_provider") as mock_gp, \
             patch("ivory_tower.templates.executor.get_executor") as mock_ge:
            mock_gp.return_value = LocalSandboxProvider()
            mock_ge.return_value = mock_executor

            gexec = GenericTemplateExecutor(template)
            outputs = gexec.run(
                run_dir=run_dir,
                agents=["agent-a", "agent-b"],
                synthesizer="synth",
                sandbox_backend="local",
                executor_name="mock",
                topic="Test",
            )

        assert "analysis" in outputs
        phase_out = outputs["analysis"]

        # Both agents have outputs
        assert "agent-a" in phase_out
        assert "agent-b" in phase_out

        # Canonical path format
        assert phase_out["agent-a"] == run_dir / "analysis" / "agent-a-analysis.md"
        assert phase_out["agent-b"] == run_dir / "analysis" / "agent-b-analysis.md"

        # Files exist and have content
        assert phase_out["agent-a"].read_text() == "Report from agent-a"
        assert phase_out["agent-b"].read_text() == "Report from agent-b"


class TestIterativePhaseExecution:
    """Iterative phase: runs rounds, blackboard grows between rounds."""

    def test_iterative_phase_blackboard_grows(self, tmp_path: Path) -> None:
        bb_config = BlackboardConfig(
            name="transcript",
            file="transcript.md",
            access="append",
        )
        phases = [
            _make_phase(
                name="debate",
                isolation="blackboard",
                agents="all",
                output="{agent}-round-{round}.md",
                rounds=3,
                blackboard=bb_config,
            ),
        ]
        template = _make_template(phases)
        run_dir = tmp_path / "run-003"
        run_dir.mkdir()

        mock_executor = MockExecutor()

        with patch("ivory_tower.templates.executor.get_provider") as mock_gp, \
             patch("ivory_tower.templates.executor.get_executor") as mock_ge:
            mock_gp.return_value = LocalSandboxProvider()
            mock_ge.return_value = mock_executor

            gexec = GenericTemplateExecutor(template)
            outputs = gexec.run(
                run_dir=run_dir,
                agents=["alice", "bob"],
                synthesizer="synth",
                sandbox_backend="local",
                executor_name="mock",
                topic="Testing",
            )

        phase_out = outputs["debate"]

        # 3 rounds x 2 agents = 6 entries
        assert len(phase_out) == 6
        assert "alice-round-1" in phase_out
        assert "bob-round-1" in phase_out
        assert "alice-round-3" in phase_out
        assert "bob-round-3" in phase_out

        # Blackboard volume should have accumulated content
        bb_path = run_dir / "volumes" / "transcript" / "transcript.md"
        assert bb_path.exists()
        bb_content = bb_path.read_text()

        # Should contain contributions from all rounds
        assert "alice" in bb_content.lower() or "alice" in bb_content
        assert "bob" in bb_content.lower() or "bob" in bb_content


class TestPhaseOutputFeedingForward:
    """Phase outputs from earlier phases feed into later phases via input_from."""

    def test_input_from_feeds_outputs_to_later_phase(self, tmp_path: Path) -> None:
        phases = [
            _make_phase(
                name="research",
                isolation="full",
                agents="all",
                output="{agent}-research.md",
            ),
            _make_phase(
                name="synthesis",
                isolation="read-all",
                agents=["synthesizer"],
                output="synthesis.md",
                input_from=["research"],
            ),
        ]
        template = _make_template(phases)
        run_dir = tmp_path / "run-004"
        run_dir.mkdir()

        mock_executor = MockExecutor()

        with patch("ivory_tower.templates.executor.get_provider") as mock_gp, \
             patch("ivory_tower.templates.executor.get_executor") as mock_ge:
            mock_gp.return_value = LocalSandboxProvider()
            mock_ge.return_value = mock_executor

            gexec = GenericTemplateExecutor(template)
            outputs = gexec.run(
                run_dir=run_dir,
                agents=["alice", "bob"],
                synthesizer="judge",
                sandbox_backend="local",
                executor_name="mock",
                topic="AI",
            )

        # Both phases produced outputs
        assert "research" in outputs
        assert "synthesis" in outputs

        # Research outputs exist
        assert outputs["research"]["alice"].exists()
        assert outputs["research"]["bob"].exists()

        # Synthesis output exists
        assert outputs["synthesis"]["judge"].exists()

        # The synthesizer's sandbox should have received the research inputs
        # (We verify this indirectly via the output files existing)
        synth_sandbox_dir = run_dir / "sandboxes" / "judge" / "workspace"
        assert (synth_sandbox_dir / "inputs" / "research" / "alice.md").exists()
        assert (synth_sandbox_dir / "inputs" / "research" / "bob.md").exists()


class TestSynthesizerOnlyPhase:
    """Synthesizer-only phases work correctly (agents: [synthesizer])."""

    def test_synthesizer_only_phase(self, tmp_path: Path) -> None:
        phases = [
            _make_phase(
                name="opening",
                isolation="full",
                agents="all",
                output="{agent}-opening.md",
            ),
            _make_phase(
                name="verdict",
                isolation="read-all",
                agents=["synthesizer"],
                output="verdict.md",
                input_from=["opening"],
            ),
        ]
        template = _make_template(phases)
        run_dir = tmp_path / "run-005"
        run_dir.mkdir()

        mock_executor = MockExecutor()

        with patch("ivory_tower.templates.executor.get_provider") as mock_gp, \
             patch("ivory_tower.templates.executor.get_executor") as mock_ge:
            mock_gp.return_value = LocalSandboxProvider()
            mock_ge.return_value = mock_executor

            gexec = GenericTemplateExecutor(template)
            outputs = gexec.run(
                run_dir=run_dir,
                agents=["alice", "bob"],
                synthesizer="judge",
                sandbox_backend="local",
                executor_name="mock",
                topic="Topic",
            )

        # Verdict phase should have exactly one agent: the synthesizer
        assert "verdict" in outputs
        verdict_out = outputs["verdict"]
        assert "judge" in verdict_out
        assert len(verdict_out) == 1
        assert verdict_out["judge"].exists()
        assert verdict_out["judge"].read_text() == "Report from judge"


class TestSandboxCleanup:
    """Cleanup: sandboxes are destroyed after execution."""

    def test_destroy_called_on_all_sandboxes(self, tmp_path: Path) -> None:
        phases = [
            _make_phase(
                name="single",
                isolation="full",
                agents="all",
                output="{agent}-out.md",
            ),
        ]
        template = _make_template(phases)
        run_dir = tmp_path / "run-006"
        run_dir.mkdir()

        mock_executor = MockExecutor()

        # Track destroy calls
        destroyed = []
        real_provider = LocalSandboxProvider()

        class TrackingProvider:
            name = "local"

            def create_sandbox(self, *args, **kwargs):
                sandbox = real_provider.create_sandbox(*args, **kwargs)
                original_destroy = sandbox.destroy

                def tracked_destroy():
                    destroyed.append(sandbox.agent_name)
                    return original_destroy()

                sandbox.destroy = tracked_destroy
                return sandbox

            def create_shared_volume(self, *args, **kwargs):
                return real_provider.create_shared_volume(*args, **kwargs)

            def destroy_all(self, run_id):
                return real_provider.destroy_all(run_id)

            @staticmethod
            def is_available():
                return True

        with patch("ivory_tower.templates.executor.get_provider") as mock_gp, \
             patch("ivory_tower.templates.executor.get_executor") as mock_ge:
            mock_gp.return_value = TrackingProvider()
            mock_ge.return_value = mock_executor

            gexec = GenericTemplateExecutor(template)
            gexec.run(
                run_dir=run_dir,
                agents=["alice", "bob"],
                synthesizer="synth",
                sandbox_backend="local",
                executor_name="mock",
                topic="Test",
            )

        assert "alice" in destroyed
        assert "bob" in destroyed

    def test_destroy_called_even_on_error(self, tmp_path: Path) -> None:
        phases = [
            _make_phase(
                name="failing",
                isolation="full",
                agents="all",
                output="{agent}-out.md",
            ),
        ]
        template = _make_template(phases)
        run_dir = tmp_path / "run-007"
        run_dir.mkdir()

        destroyed = []
        real_provider = LocalSandboxProvider()

        class TrackingProvider:
            name = "local"

            def create_sandbox(self, *args, **kwargs):
                sandbox = real_provider.create_sandbox(*args, **kwargs)
                original_destroy = sandbox.destroy

                def tracked_destroy():
                    destroyed.append(sandbox.agent_name)
                    return original_destroy()

                sandbox.destroy = tracked_destroy
                return sandbox

            def create_shared_volume(self, *args, **kwargs):
                return real_provider.create_shared_volume(*args, **kwargs)

            def destroy_all(self, run_id):
                return real_provider.destroy_all(run_id)

            @staticmethod
            def is_available():
                return True

        class FailingExecutor:
            name = "failing"

            def run(self, *args, **kwargs):
                raise RuntimeError("Executor failed")

        with patch("ivory_tower.templates.executor.get_provider") as mock_gp, \
             patch("ivory_tower.templates.executor.get_executor") as mock_ge:
            mock_gp.return_value = TrackingProvider()
            mock_ge.return_value = FailingExecutor()

            gexec = GenericTemplateExecutor(template)
            with pytest.raises(RuntimeError, match="Executor failed"):
                gexec.run(
                    run_dir=run_dir,
                    agents=["alice"],
                    synthesizer="synth",
                    sandbox_backend="local",
                    executor_name="mock",
                    topic="Test",
                )

        # Despite the error, destroy was still called
        assert "alice" in destroyed


class TestOutputFilenamePatterns:
    """Output filenames use template patterns ({agent}, {round})."""

    def test_agent_pattern_in_output(self, tmp_path: Path) -> None:
        phases = [
            _make_phase(
                name="analysis",
                isolation="full",
                agents="all",
                output="{agent}-analysis.md",
            ),
        ]
        template = _make_template(phases)
        run_dir = tmp_path / "run-008"
        run_dir.mkdir()

        mock_executor = MockExecutor()

        with patch("ivory_tower.templates.executor.get_provider") as mock_gp, \
             patch("ivory_tower.templates.executor.get_executor") as mock_ge:
            mock_gp.return_value = LocalSandboxProvider()
            mock_ge.return_value = mock_executor

            gexec = GenericTemplateExecutor(template)
            outputs = gexec.run(
                run_dir=run_dir,
                agents=["claude", "gpt4"],
                synthesizer="synth",
                sandbox_backend="local",
                executor_name="mock",
                topic="Test",
            )

        assert outputs["analysis"]["claude"].name == "claude-analysis.md"
        assert outputs["analysis"]["gpt4"].name == "gpt4-analysis.md"

    def test_agent_round_pattern_in_iterative_output(self, tmp_path: Path) -> None:
        bb_config = BlackboardConfig(
            name="transcript",
            file="t.md",
            access="append",
        )
        phases = [
            _make_phase(
                name="debate",
                isolation="blackboard",
                agents="all",
                output="{agent}-round-{round}.md",
                rounds=2,
                blackboard=bb_config,
            ),
        ]
        template = _make_template(phases)
        run_dir = tmp_path / "run-009"
        run_dir.mkdir()

        mock_executor = MockExecutor()

        with patch("ivory_tower.templates.executor.get_provider") as mock_gp, \
             patch("ivory_tower.templates.executor.get_executor") as mock_ge:
            mock_gp.return_value = LocalSandboxProvider()
            mock_ge.return_value = mock_executor

            gexec = GenericTemplateExecutor(template)
            outputs = gexec.run(
                run_dir=run_dir,
                agents=["alice"],
                synthesizer="synth",
                sandbox_backend="local",
                executor_name="mock",
                topic="Test",
            )

        debate_out = outputs["debate"]
        # Round filenames use {agent} and {round}
        assert debate_out["alice-round-1"].name == "alice-round-1.md"
        assert debate_out["alice-round-2"].name == "alice-round-2.md"

    def test_static_output_name(self, tmp_path: Path) -> None:
        """Output pattern without {agent} placeholder -- e.g. verdict.md."""
        phases = [
            _make_phase(
                name="verdict",
                isolation="full",
                agents=["synthesizer"],
                output="verdict.md",
            ),
        ]
        template = _make_template(phases)
        run_dir = tmp_path / "run-010"
        run_dir.mkdir()

        mock_executor = MockExecutor()

        with patch("ivory_tower.templates.executor.get_provider") as mock_gp, \
             patch("ivory_tower.templates.executor.get_executor") as mock_ge:
            mock_gp.return_value = LocalSandboxProvider()
            mock_ge.return_value = mock_executor

            gexec = GenericTemplateExecutor(template)
            outputs = gexec.run(
                run_dir=run_dir,
                agents=["alice"],
                synthesizer="judge",
                sandbox_backend="local",
                executor_name="mock",
                topic="Test",
            )

        assert outputs["verdict"]["judge"].name == "verdict.md"
