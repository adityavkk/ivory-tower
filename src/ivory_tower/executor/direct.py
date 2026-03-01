"""Direct LLM API executor via litellm."""

from __future__ import annotations

import time
from typing import Any

from ivory_tower.sandbox.types import Sandbox

from .types import AgentOutput


class DirectExecutor:
    """Executes agents by calling LLM APIs directly via litellm.

    Requires litellm to be installed (optional dependency).
    """

    name = "direct"

    def run(
        self,
        sandbox: Sandbox,
        agent_name: str,
        prompt: str,
        output_dir: str,
        model: str | None = None,
        system_prompt: str | None = None,
        verbose: bool = False,
    ) -> AgentOutput:
        try:
            import litellm
        except ImportError:
            raise RuntimeError(
                "The direct executor requires litellm. Install: uv add litellm"
            )

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        start = time.monotonic()
        response = litellm.completion(
            model=model or agent_name,
            messages=messages,
        )
        elapsed = time.monotonic() - start

        report_text = response.choices[0].message.content or ""

        # Write result to sandbox
        report_path = f"{output_dir}/{agent_name}-report.md"
        sandbox.write_file(report_path, report_text)

        return AgentOutput(
            report_path=report_path,
            raw_output=report_text,
            duration_seconds=elapsed,
            metadata={
                "model": model or agent_name,
                "usage": getattr(response, "usage", None),
            },
        )
