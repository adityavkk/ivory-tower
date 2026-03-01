"""Tests for prompt template generation."""

from ivory_tower.prompts import (
    build_refinement_prompt,
    build_research_prompt,
    build_synthesis_prompt,
)


class TestBuildResearchPrompt:
    def test_research_prompt_raw(self):
        """raw=True returns topic unchanged."""
        topic = "What is the state of quantum computing in 2026?"
        result = build_research_prompt(topic, raw=True)
        assert result == topic

    def test_research_prompt_default(self):
        """Default prompt contains header, topic, and methodology."""
        topic = "Rust vs Go for backend services"
        result = build_research_prompt(topic)
        assert "# Deep Research Task" in result
        assert topic in result
        assert "## Methodology" in result
        assert "primary sources" in result
        assert "## Output Requirements" in result

    def test_research_prompt_with_instructions(self):
        """Custom instructions appear in Additional Instructions section."""
        topic = "Edge computing trends"
        instructions = "Focus on cost analysis and vendor comparison"
        result = build_research_prompt(topic, instructions=instructions)
        assert "## Additional Instructions" in result
        assert instructions in result

    def test_research_prompt_no_instructions(self):
        """No Additional Instructions section when instructions=None."""
        topic = "Edge computing trends"
        result = build_research_prompt(topic)
        assert "Additional Instructions" not in result


class TestBuildRefinementPrompt:
    def test_refinement_prompt_contains_all_parts(self):
        """All substitution values appear in output."""
        topic = "AI safety research"
        own_report = "My detailed findings on AI safety..."
        peer_report = "Peer findings on alignment problems..."
        peer_name = "codex-5.3-xhigh"

        result = build_refinement_prompt(topic, own_report, peer_report, peer_name)

        assert topic in result
        assert own_report in result
        assert peer_report in result
        assert peer_name in result

    def test_refinement_prompt_has_critical_rules(self):
        """Critical Rules section exists in refinement prompt."""
        result = build_refinement_prompt(
            "topic", "own report", "peer report", "peer-agent"
        )
        assert "## Critical Rules" in result


class TestBuildSynthesisPrompt:
    def test_synthesis_prompt_contains_all_sections(self):
        """All required section headers and substituted values present."""
        topic = "Future of WebAssembly"
        agent_count = 3
        reports = "## Agent A\nFindings...\n## Agent B\nFindings..."

        result = build_synthesis_prompt(topic, agent_count, reports)

        assert topic in result
        assert reports in result
        # All 8 required final-report sections mentioned in synthesis prompt
        for section in [
            "Executive Summary",
            "Key Findings",
            "Areas of Consensus",
            "Areas of Disagreement",
            "Novel Insights",
            "Open Questions",
            "Sources",
            "Methodology",
        ]:
            assert section in result, f"Missing section: {section}"

    def test_synthesis_prompt_agent_count_formatting(self):
        """agent_count rendered as string in the output."""
        result = build_synthesis_prompt("topic", 5, "reports here")
        assert "5" in result
