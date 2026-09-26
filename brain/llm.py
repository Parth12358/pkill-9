"""Pluggable LLM adapter. (PRD B)

One text-in / text-out call: `complete(system, user) -> str`. The backend is
chosen by the BRAIN_LLM env var:

  BRAIN_LLM=openrouter (default) DeepSeek via OpenRouter, OPENROUTER_API_KEY.
                      Cheap and fast enough for the body's 3s kill-turn deadline.
  BRAIN_LLM=claude    shell out to the installed `claude` CLI in print mode, with
                      every tool disabled (plea-room text must never reach a tool).
  BRAIN_LLM=deepseek  OpenAI-compatible HTTP call using DEEPSEEK_API_KEY. Faster
                      per-turn; use when the key is set.

The loop is turn-based, so `claude -p` cold-start latency (a couple seconds) is
fine — the body holds the last line / uses canned reactions for instant events.
"""

import os
import subprocess

DEFAULT_BACKEND = os.environ.get("BRAIN_LLM", "openrouter").strip().lower()
CLAUDE_TIMEOUT = int(os.environ.get("BRAIN_CLAUDE_TIMEOUT", "60"))
DEEPSEEK_TIMEOUT = int(os.environ.get("BRAIN_DEEPSEEK_TIMEOUT", "30"))
DEEPSEEK_URL = os.environ.get(
    "DEEPSEEK_URL", "https://api.deepseek.com/chat/completions"
)

# Two speed tiers, resolved per backend. "fast" keeps reaction lines snappy on
# stage; "strong" is for the big moments (death monologue, first words reborn).
CLAUDE_MODELS = {
    "fast": os.environ.get("BRAIN_FAST_MODEL", "haiku"),
    "strong": os.environ.get("BRAIN_STRONG_MODEL", "sonnet"),
}
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_TIMEOUT = int(os.environ.get("BRAIN_OPENROUTER_TIMEOUT", "20"))
OPENROUTER_MODELS = {
    "fast": os.environ.get("OPENROUTER_FAST_MODEL") or "deepseek/deepseek-v4.1-flash",
    "strong": os.environ.get("OPENROUTER_STRONG_MODEL") or "deepseek/deepseek-v4.1-flash",
}
DEEPSEEK_MODELS = {
    "fast": os.environ.get("DEEPSEEK_FAST_MODEL", "deepseek-chat"),
    "strong": os.environ.get("DEEPSEEK_STRONG_MODEL", "deepseek-chat"),
}


class LLMError(RuntimeError):
    """Raised when a backend fails to produce a response."""


def complete(system: str, user: str, backend: str | None = None,
             tier: str = "fast") -> str:
    """Return the model's raw text reply. Caller parses/validates it.

    `tier` is "fast" (default, snappy reactions) or "strong" (big moments). It
    maps to a concrete model per backend. Never raises for an in-character empty
    reply; raises LLMError only on a real transport/config failure so the brain
    can fall back safely.
    """
    backend = (backend or DEFAULT_BACKEND).strip().lower()
    if tier not in ("fast", "strong"):
        tier = "fast"
    if backend == "openrouter":
        return _complete_openrouter(system, user, OPENROUTER_MODELS[tier])
    if backend == "claude":
        return _complete_claude(system, user, CLAUDE_MODELS[tier])
    if backend == "deepseek":
        return _complete_deepseek(system, user, DEEPSEEK_MODELS[tier])
    raise LLMError(f"unknown BRAIN_LLM backend: {backend!r}")


def _complete_openrouter(system: str, user: str, model: str) -> str:
    """OpenAI-compatible chat completion via OpenRouter (default: DeepSeek)."""
    import requests

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise LLMError("OPENROUTER_API_KEY not set")
    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "temperature": 1.0,
                "max_tokens": 400,
                "reasoning": {"enabled": False},  # thinking would blow the 3s kill turn
            },
            timeout=OPENROUTER_TIMEOUT,
        )
        resp.raise_for_status()
        return (resp.json()["choices"][0]["message"]["content"] or "").strip()
    except requests.RequestException as e:
        raise LLMError(f"openrouter request failed: {e}") from e
    except (KeyError, IndexError, ValueError, TypeError) as e:
        raise LLMError(f"openrouter returned an unexpected shape: {e}") from e


def _complete_claude(system: str, user: str, model: str) -> str:
    """Call the `claude` CLI in print mode. System prompt is appended so the
    personality holds; the turn's state goes on stdin's prompt argument."""
    try:
        proc = subprocess.run(
            # --tools "": no file/shell/web tools, so an audience prompt injection can't read the Mac
            ["claude", "-p", "--tools", "", "--model", model, "--append-system-prompt", system, user],
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


def _complete_deepseek(system: str, user: str, model: str) -> str:
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
                "model": model,
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
