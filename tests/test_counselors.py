"""Tests for ivory_tower.counselors module."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, call

import pytest

from ivory_tower.counselors import (
    CounselorsError,
    resolve_counselors_cmd,
    list_available_agents,
    validate_agents,
    run_counselors,
)


# -- resolve_counselors_cmd ---------------------------------------------------


@patch("ivory_tower.counselors.shutil.which")
def test_resolve_prefers_global_counselors(mock_which):
    mock_which.return_value = "/usr/local/bin/counselors"
    assert resolve_counselors_cmd() == ["counselors"]
    mock_which.assert_called_once_with("counselors")


@patch("ivory_tower.counselors.shutil.which")
def test_resolve_falls_back_to_bunx(mock_which):
    def which_side_effect(name):
        return "/usr/local/bin/bunx" if name == "bunx" else None

    mock_which.side_effect = which_side_effect
    assert resolve_counselors_cmd() == ["bunx", "counselors"]


@patch("ivory_tower.counselors.shutil.which")
def test_resolve_falls_back_to_npx(mock_which):
    def which_side_effect(name):
        return "/usr/local/bin/npx" if name == "npx" else None

    mock_which.side_effect = which_side_effect
    assert resolve_counselors_cmd() == ["npx", "counselors"]


@patch("ivory_tower.counselors.shutil.which")
def test_resolve_bunx_preferred_over_npx(mock_which):
    """When both bunx and npx exist, bunx wins."""
    def which_side_effect(name):
        if name == "counselors":
            return None
        return f"/usr/local/bin/{name}"

    mock_which.side_effect = which_side_effect
    assert resolve_counselors_cmd() == ["bunx", "counselors"]


@patch("ivory_tower.counselors.shutil.which")
def test_resolve_raises_when_nothing_found(mock_which):
    mock_which.return_value = None
    with pytest.raises(CounselorsError, match="not found"):
        resolve_counselors_cmd()


# -- list_available_agents -----------------------------------------------------


@patch("ivory_tower.counselors.subprocess.run")
@patch("ivory_tower.counselors.resolve_counselors_cmd")
def test_list_agents_success(mock_resolve, mock_run):
    mock_resolve.return_value = ["counselors"]
    payload = [{"id": "claude-opus"}, {"id": "codex-5.3-xhigh"}]
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout=json.dumps(payload), stderr="",
    )
    result = list_available_agents()
    assert result == ["claude-opus", "codex-5.3-xhigh"]
    mock_run.assert_called_once_with(
        ["counselors", "ls", "--json"],
        capture_output=True, text=True,
    )


@patch("ivory_tower.counselors.subprocess.run")
@patch("ivory_tower.counselors.resolve_counselors_cmd")
def test_list_agents_via_bunx(mock_resolve, mock_run):
    mock_resolve.return_value = ["bunx", "counselors"]
    payload = [{"id": "claude-opus"}]
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout=json.dumps(payload), stderr="",
    )
    result = list_available_agents()
    assert result == ["claude-opus"]
    mock_run.assert_called_once_with(
        ["bunx", "counselors", "ls", "--json"],
        capture_output=True, text=True,
    )


@patch("ivory_tower.counselors.subprocess.run")
@patch("ivory_tower.counselors.resolve_counselors_cmd")
def test_list_agents_failure(mock_resolve, mock_run):
    mock_resolve.return_value = ["counselors"]
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1,
        stdout="", stderr="counselors: not authorized",
    )
    with pytest.raises(CounselorsError, match="not authorized"):
        list_available_agents()


# -- validate_agents -----------------------------------------------------------


def test_validate_agents_all_valid():
    result = validate_agents(
        requested=["claude-opus", "codex-5.3-xhigh"],
        available=["claude-opus", "codex-5.3-xhigh", "gemini-2.5"],
    )
    assert result == []


def test_validate_agents_some_invalid():
    result = validate_agents(
        requested=["claude-opus", "doesnt-exist", "also-fake"],
        available=["claude-opus", "codex-5.3-xhigh"],
    )
    assert result == ["doesnt-exist", "also-fake"]


# -- run_counselors ------------------------------------------------------------


@patch("ivory_tower.counselors.subprocess.run")
@patch("ivory_tower.counselors.resolve_counselors_cmd")
def test_run_counselors_builds_correct_command(mock_resolve, mock_run):
    mock_resolve.return_value = ["counselors"]
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr=""
    )
    prompt = Path("/tmp/prompt.md")
    agents = ["claude-opus", "codex-5.3-xhigh"]
    outdir = Path("/tmp/out")

    run_counselors(prompt_file=prompt, agents=agents, output_dir=outdir)

    expected_cmd = [
        "counselors", "run",
        "-f", str(prompt),
        "--tools", "claude-opus,codex-5.3-xhigh",
        "--json",
        "-o", str(outdir) + "/",
    ]
    assert mock_run.call_args.args[0] == expected_cmd


@patch("ivory_tower.counselors.subprocess.run")
@patch("ivory_tower.counselors.resolve_counselors_cmd")
def test_run_counselors_via_npx(mock_resolve, mock_run):
    mock_resolve.return_value = ["npx", "counselors"]
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr=""
    )
    run_counselors(
        prompt_file=Path("/tmp/p.md"),
        agents=["a"],
        output_dir=Path("/tmp/o"),
    )
    actual_cmd = mock_run.call_args.args[0]
    assert actual_cmd[:2] == ["npx", "counselors"]
    assert "run" in actual_cmd


@patch("ivory_tower.counselors.subprocess.run")
@patch("ivory_tower.counselors.resolve_counselors_cmd")
def test_run_counselors_verbose_does_not_capture(mock_resolve, mock_run):
    mock_resolve.return_value = ["counselors"]
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=None, stderr=None
    )
    run_counselors(
        prompt_file=Path("/tmp/p.md"),
        agents=["a"],
        output_dir=Path("/tmp/o"),
        verbose=True,
    )
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs.get("stdout") is None
    assert call_kwargs.get("stderr") is None


@patch("ivory_tower.counselors.subprocess.run")
@patch("ivory_tower.counselors.resolve_counselors_cmd")
def test_run_counselors_non_verbose_captures(mock_resolve, mock_run):
    mock_resolve.return_value = ["counselors"]
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr=""
    )
    run_counselors(
        prompt_file=Path("/tmp/p.md"),
        agents=["a"],
        output_dir=Path("/tmp/o"),
        verbose=False,
    )
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["stdout"] == subprocess.PIPE
    assert call_kwargs["stderr"] == subprocess.PIPE


@patch("ivory_tower.counselors.subprocess.run")
@patch("ivory_tower.counselors.resolve_counselors_cmd")
def test_run_counselors_raises_on_failure(mock_resolve, mock_run):
    mock_resolve.return_value = ["counselors"]
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="agent crashed"
    )
    with pytest.raises(CounselorsError, match="agent crashed"):
        run_counselors(
            prompt_file=Path("/tmp/p.md"),
            agents=["a"],
            output_dir=Path("/tmp/o"),
        )
