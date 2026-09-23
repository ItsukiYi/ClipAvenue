"""ClipAgent — headless LLM agent driving the clip intelligence steps.

A minimal agent loop over the Anthropic SDK. The agent reads a skill file as
its system prompt, calls mechanical tools (clip_tools.py), and performs the
four intelligence steps (ASR correction, segmentation, clip selection, title/
tags/cover) inline by writing JSON artifacts to the project directory.

Runtime wiring:
  - ANTHROPIC_BASE_URL   : the API endpoint (reuses the VSCode extension's endpoint)
  - ANTHROPIC_AUTH_TOKEN  : auth token
  - ANTHROPIC_MODEL       : model id to call
These are already set in this machine's environment — no new credentials needed.

Why a hand-rolled loop and not the Agent SDK: `claude` is not on PATH and no
agent SDK is installed in this venv, but the Anthropic-compatible endpoint is
configured via env vars. A ~60-line tool-use loop is all the runtime we need;
the skill is what makes it stable, not a heavy framework.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

from clipavenue.logger import log

# ---------------------------------------------------------------------------
# Client construction — from env vars only
# ---------------------------------------------------------------------------

SKILL_PATH = Path(__file__).resolve().parent.parent / "skills" / "clipavenue" / "clip-workflow.md"

MAX_TOOL_RESULT_CHARS = 10000  # truncate oversized tool results
DEFAULT_MAX_STEPS = 40  # cap tool-use rounds to avoid runaway loops


def _make_client():
    """Build an Anthropic client from ANTHROPIC_* env vars. No hardcoding.

    ANTHROPIC_AUTH_TOKEN → Bearer auth (what Claude Code relays expect).
    Falls back to ANTHROPIC_API_KEY → x-api-key (Anthropic-native) if the
    bearer token isn't set.
    """
    from anthropic import Anthropic  # local import; SDK installed in Phase 1

    base_url = os.environ.get("ANTHROPIC_BASE_URL") or None
    auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if auth_token:
        return Anthropic(base_url=base_url, auth_token=auth_token)
    return Anthropic(base_url=base_url, api_key=api_key or "")


def _model() -> str:
    m = os.environ.get("ANTHROPIC_MODEL")
    if not m:
        raise RuntimeError(
            "ANTHROPIC_MODEL not set — cannot run headless agent. "
            "Set it (and ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN) in the environment."
        )
    # Strip VSCode extension display suffix like [1M] from the model name.
    # Clean model slug is everything before the first "[", whitespace-stripped.
    m = m.split("[", 1)[0].strip()
    if not m:
        raise RuntimeError(f"ANTHROPIC_MODEL='{os.environ.get('ANTHROPIC_MODEL')}' resolved to empty slug")
    return m


# A tool the agent can call. `spec` is the JSON schema handed to the API.
class Tool:
    def __init__(self, name: str, description: str, spec: dict, fn: Callable[[dict], Any]) -> None:
        self.name = name
        self.description = description
        self.spec = spec
        self.fn = fn

    def call(self, params: dict) -> str:
        try:
            result = self.fn(params)
            # Tools return either a string or a JSON-serializable value.
            if isinstance(result, str):
                return result
            return json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            log.error("agent", f"tool {self.name} failed: {exc}")
            return json.dumps({"error": str(exc)}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# ClipAgent
# ---------------------------------------------------------------------------

class ClipAgent:
    """Runs the clip workflow as a headless tool-use loop.

    The skill file is the source of truth for procedure; this class is just
    the runtime that executes it.
    """

    def __init__(
        self,
        system_prompt: str,
        tools: list[Tool],
        max_steps: int = DEFAULT_MAX_STEPS,
        client: Any = None,
    ) -> None:
        self.system_prompt = system_prompt
        self.tools = {t.name: t for t in tools}
        self.tool_specs = [
            {"name": t.name, "description": t.description, "input_schema": t.spec}
            for t in tools
        ]
        self.max_steps = max_steps
        self.client = client or _make_client()
        self.model = _model()
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    # -- load from skill ----------------------------------------------------

    @classmethod
    def from_skill(cls, tools: list[Tool], skill_path: Path = SKILL_PATH, **kw) -> "ClipAgent":
        if not skill_path.is_file():
            raise FileNotFoundError(
                f"skill not found: {skill_path}. Author it before running the agent."
            )
        system = skill_path.read_text(encoding="utf-8")
        return cls(system_prompt=system, tools=tools, **kw)

    # -- the loop -----------------------------------------------------------

    def run(self, user_message: str) -> dict:
        """Run the agent loop until it stops calling tools.

        Returns {text, steps, tokens}. Raises on API error or step cap hit
        (the worker turns these into retries).
        """
        messages: list[dict] = [{"role": "user", "content": user_message}]
        steps = 0
        final_text = ""

        while steps < self.max_steps:
            steps += 1
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt,
                tools=self.tool_specs or None,
                messages=messages,
            )
            self._track_tokens(resp)

            # If the model wants to call tools, execute them and continue.
            if resp.stop_reason == "tool_use":
                # Convert SDK ContentBlock objects to plain dicts (gateway
                # compatibility — some non-Anthropic gateways can't parse
                # the SDK's serialized format).
                assistant_content = []
                for b in resp.content:
                    if b.type == "text":
                        assistant_content.append({"type": "text", "text": b.text})
                    elif b.type == "tool_use":
                        assistant_content.append({
                            "type": "tool_use", "id": b.id,
                            "name": b.name, "input": b.input,
                        })
                messages.append({"role": "assistant", "content": assistant_content})
                tool_results = []
                for block in resp.content:
                    if block.type == "tool_use":
                        # block.input may be a JSON string (non-Anthropic gateways)
                        # or a dict (Anthropic-native). Handle both.
                        params = block.input
                        if isinstance(params, str):
                            try:
                                params = json.loads(params)
                            except json.JSONDecodeError:
                                pass
                        log.info("agent", f"tool_use: {block.name} ({_short(params)})")
                        output = self.tools[block.name].call(params)
                        # Truncate oversized tool results to avoid gateway limits
                        if len(output) > MAX_TOOL_RESULT_CHARS:
                            output = output[:MAX_TOOL_RESULT_CHARS] + "\n…truncated"
                        # Some gateways require content as a list of content blocks
                        # rather than a plain string. Wrap to be safe.
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": [{"type": "text", "text": output}],
                        })
                messages.append({"role": "user", "content": tool_results})
                continue

            # Otherwise the model is done — collect text and stop.
            final_text = "".join(b.text for b in resp.content if b.type == "text")
            break
        else:
            raise RuntimeError(f"agent hit step cap ({self.max_steps}) without finishing")

        return {
            "text": final_text,
            "steps": steps,
            "input_tokens": self._total_input_tokens,
            "output_tokens": self._total_output_tokens,
        }

    def _track_tokens(self, resp) -> None:
        usage = getattr(resp, "usage", None)
        if not usage:
            return
        self._total_input_tokens += getattr(usage, "input_tokens", 0) or 0
        self._total_output_tokens += getattr(usage, "output_tokens", 0) or 0

    # -- smoke test ---------------------------------------------------------

    @classmethod
    def smoke(cls) -> dict:
        """Verify the endpoint is reachable and the model responds.

        No tools, no skill — just one round-trip. Run via:
            python -c "from clipavenue.agent import ClipAgent; ClipAgent.smoke()"
        """
        client = _make_client()
        model = _model()
        log.info("agent", f"smoke: model={model} base_url={os.environ.get('ANTHROPIC_BASE_URL','(default)')}")
        resp = client.messages.create(
            model=model,
            max_tokens=64,
            messages=[{"role": "user", "content": "回复两个字：在的"}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        usage = getattr(resp, "usage", None)
        result = {
            "ok": True,
            "model": model,
            "text": text.strip(),
            "input_tokens": getattr(usage, "input_tokens", 0),
            "output_tokens": getattr(usage, "output_tokens", 0),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result


def _short(obj: Any, limit: int = 120) -> str:
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return s if len(s) <= limit else s[:limit] + "…"


# Allow `python -m clipavenue.agent` for a quick connectivity check.
if __name__ == "__main__":
    ClipAgent.smoke()
