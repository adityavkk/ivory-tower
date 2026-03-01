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
        peer_reports = "### codex-5.3-xhigh\n\nPeer findings on alignment problems..."

        result = build_refinement_prompt(topic, own_report, peer_reports)

        assert topic in result
        assert own_report in result
        assert "Peer findings on alignment problems..." in result
        assert "codex-5.3-xhigh" in result

    def test_refinement_prompt_has_critical_rules(self):
        """Critical Rules section exists in refinement prompt."""
        result = build_refinement_prompt(
            "topic", "own report", "### peer-agent\n\npeer report"
        )
        assert "## Critical Rules" in result

    def test_refinement_prompt_requests_standalone_report(self):
        """Refinement prompt asks for a complete standalone report, not a diff."""
        result = build_refinement_prompt(
            "topic", "own report", "### peer\n\npeer report"
        )
        assert "standalone report" in result.lower()
        assert "## Output Structure" in result


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
            "Background & Context",
            "Key Findings",
            "Areas of Consensus",
            "Areas of Disagreement",
            "Open Questions",
            "Sources",
            "Methodology",
        ]:
            assert section in result, f"Missing section: {section}"

    def test_synthesis_prompt_agent_count_formatting(self):
        """agent_count rendered as string in the output."""
        result = build_synthesis_prompt("topic", 5, "reports here")
        assert "5" in result


class TestFormatList:
    def test_empty_list(self):
        from ivory_tower.prompts import _format_list
        assert _format_list([]) == "- (none provided)"

    def test_single_item(self):
        from ivory_tower.prompts import _format_list
        assert _format_list(["a"]) == "- a"

    def test_multiple_items(self):
        from ivory_tower.prompts import _format_list
        result = _format_list(["a", "b"])
        assert result == "- a\n- b"


class TestBuildJudgingPrompt:
    def test_contains_topic_and_report(self):
        from ivory_tower.prompts import build_judging_prompt
        result = build_judging_prompt("AI safety", "This is a report about AI safety.")
        assert "AI safety" in result
        assert "This is a report about AI safety." in result
        assert "Factual Accuracy" in result
        assert "JSON" in result


class TestBuildImprovementPrompt:
    def test_contains_all_feedback_fields(self):
        from ivory_tower.prompts import build_improvement_prompt
        feedback = {
            "score": 5.0,
            "dimensions": {
                "factual_accuracy": 6,
                "depth_of_analysis": 5,
                "source_quality": 4,
                "coverage_breadth": 5,
                "analytical_rigor": 5,
            },
            "strengths": ["good structure"],
            "weaknesses": ["weak sources"],
            "suggestions": ["add more references"],
            "critique": "Needs more depth.",
        }
        result = build_improvement_prompt("AI safety", "current report", feedback, 3)
        assert "Round 3" in result
        assert "AI safety" in result
        assert "current report" in result
        assert "5.0/10" in result
        assert "good structure" in result
        assert "weak sources" in result
        assert "add more references" in result
        assert "Needs more depth." in result

    def test_empty_feedback_defaults(self):
        from ivory_tower.prompts import build_improvement_prompt
        result = build_improvement_prompt("topic", "report", {}, 1)
        assert "(none provided)" in result
        assert "(no critique provided)" in result


class TestBuildAdversarialSynthesisPrompt:
    def test_contains_all_parts(self):
        from ivory_tower.prompts import build_adversarial_synthesis_prompt
        result = build_adversarial_synthesis_prompt(
            topic="AI safety",
            agent_a="claude",
            optimized_report_a="Report A content",
            score_a=7.5,
            agent_b="codex",
            optimized_report_b="Report B content",
            score_b=8.0,
            total_rounds=10,
        )
        assert "AI safety" in result
        assert "claude" in result
        assert "codex" in result
        assert "Report A content" in result
        assert "Report B content" in result
        assert "7.5" in result
        assert "8.0" in result
        assert "10" in result
        assert "Executive Summary" in result
