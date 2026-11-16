"""Talk to the local Ollama, when OLLAMA_URL is set. Off by default.

Three uses: sorting a question into a known topic key (qa.sort_with_model), writing the single
plain-language answer to a question from the checked source and chart facts (qa.ai_answer), and,
only with OLLAMA_NARRATE=1, rewording facts (narrate).
"""
from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger("samay.narrate")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
TIMEOUT_SECONDS = 20.0
# Free-form answers are longer than sorting a question, and a bigger model can be used for them.
AI_MODEL = os.environ.get("OLLAMA_QA_MODEL") or "qwen2.5:14b"
AI_TIMEOUT_SECONDS = 240.0  # allows cold CPU inference while the bot shows its typing indicator
AI_MAX_TOKENS = 1024
THINKING_MODELS = {"qwen3", "qwen3.5", "gemma4"}

SYSTEM = (
    "You write short, warm daily readings in the Jyotish tradition for a Telegram bot. "
    "Use ONLY the facts provided. Do not invent placements, yogas or events. "
    "Frame everything as traditional interpretation for reflection, not as certain prediction. "
    "Max 120 words. Plain text, no markdown."
)

_client: httpx.AsyncClient | None = None


def enabled() -> bool:
    return bool(OLLAMA_URL)


def rewording_enabled() -> bool:
    """Rewording /today facts is its own switch: it replaces the plain-words section, so it stays off even
    when the model is on for sorting and AI answers, unless OLLAMA_NARRATE=1."""
    return enabled() and os.environ.get("OLLAMA_NARRATE") == "1"


def template(facts: list[str]) -> str:
    return "\n".join(f"• {f}" for f in facts)


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
    return _client


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def complete(
    system: str,
    prompt: str,
    client: httpx.AsyncClient | None = None,
    model: str | None = None,
    timeout: float | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> str | None:
    """The model's reply, or None when the model is off, slow, failing or silent."""
    if not enabled():
        return None
    try:
        selected_model = model or OLLAMA_MODEL
        options = {
            **({"num_predict": max_tokens} if max_tokens else {}),
            **({"temperature": temperature} if temperature is not None else {}),
        }
        payload = {
            "model": selected_model,
            "system": system,
            "prompt": prompt,
            "stream": False,
            **({"think": False} if selected_model.split(":", 1)[0] in THINKING_MODELS else {}),
            **({"options": options} if options else {}),
        }
        r = await (client or _get_client()).post(
            f"{OLLAMA_URL.rstrip('/')}/api/generate",
            json=payload,
            **({} if timeout is None else {"timeout": timeout}),
        )
        r.raise_for_status()
        result = r.json()
        if result.get("done_reason") == "length":
            log.warning("model response exceeded its generation limit")
            return None
        return result.get("response", "").strip() or None
    except (httpx.HTTPError, ValueError) as e:  # nothing may fail because the LLM is down
        log.warning("model call failed: %s", type(e).__name__)
        return None


async def narrate(facts: list[str], client: httpx.AsyncClient | None = None) -> str:
    """Reworded facts, or the plain template when narration is off or the model is unavailable."""
    if not enabled():
        return template(facts)
    prompt = "Facts:\n" + "\n".join(f"- {f}" for f in facts) + "\n\nWrite today's reading."
    return await complete(SYSTEM, prompt, client) or template(facts)
