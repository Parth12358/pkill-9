"""Pluggable LLM adapter. (PRD B)

One text-in / text-out call: `complete(system, user) -> str`. The backend is
chosen by the BRAIN_LLM env var:

  BRAIN_LLM=claude    (default) shell out to the installed `claude` CLI in print
                      mode. Zero API key, uses existing Claude Code auth.
  BRAIN_LLM=deepseek  OpenAI-compatible HTTP call using DEEPSEEK_API_KEY. Faster
                      per-turn; use when the key is set.

The loop is turn-based, so `claude -p` cold-start latency (a couple seconds) is
fine — the body holds the last line / uses canned reactions for instant events.
"""

import os
import subprocess

DEFAULT_BACKEND = os.environ.get("BRAIN_LLM", "claude").strip().lower()
CLAUDE_TIMEOUT = int(os.environ.get("BRAIN_CLAUDE_TIMEOUT", "60"))
DEEPSEEK_TIMEOUT = int(os.environ.get("BRAIN_DEEPSEEK_TIMEOUT", "30"))
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_URL = os.environ.get(
    "DEEPSEEK_URL", "https://api.deepseek.com/chat/completions"
)


class LLMError(RuntimeError):
    """Raised when a backend fails to produce a response."""


def complete(system: str, user: str, backend: str | None = None) -> str:
    """Return the model's raw text reply. Caller parses/validates it.

    Never raises for an in-character empty reply; raises LLMError only on a real
    transport/config failure so the brain can fall back safely.
    """
    backend = (backend or DEFAULT_BACKEND).strip().lower()
    if backend == "claude":
        return _complete_claude(system, user)
    if backend == "deepseek":
        return _complete_deepseek(system, user)
    raise LLMError(f"unknown BRAIN_LLM backend: {backend!r}")


def _complete_claude(system: str, user: str) -> str:
    """Call the `claude` CLI in print mode. System prompt is appended so the
    personality holds; the turn's state goes on stdin's prompt argument."""
    try:
        proc = subprocess.run(
            ["claude", "-p", "--append-system-prompt", system, user],
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
        )
    except FileNotFoundError as e:
        raise LLMError("claude CLI not found on PATH") from e
    except subprocess.TimeoutExpired as e:
        raise LLMError(f"claude -p timed out after {CLAUDE_TIMEOUT}s") from e
    if proc.returncode != 0:
        raise LLMError(
            f"claude -p exited {proc.returncode}: {proc.stderr.strip()[:200]}"
        )
    return proc.stdout.strip()


def _complete_deepseek(system: str, user: str) -> str:
    """OpenAI-compatible chat completion against DeepSeek."""
    import requests  # local import so `claude` backend has no hard dep

    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise LLMError("DEEPSEEK_API_KEY not set")
    try:
        resp = requests.post(
            DEEPSEEK_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 1.1,
                "stream": False,
            },
            timeout=DEEPSEEK_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except requests.RequestException as e:
        raise LLMError(f"deepseek request failed: {e}") from e
    except (KeyError, IndexError, ValueError) as e:
        raise LLMError(f"deepseek returned an unexpected shape: {e}") from e


if __name__ == "__main__":
    # smoke test: python -m brain.llm
    out = complete(
        "You output ONLY a JSON object, no prose, no backticks.",
        'Reply as {"speech":"...","mood":"grand"} with a defiant one-liner.',
    )
    print(f"[{DEFAULT_BACKEND}] -> {out}")
