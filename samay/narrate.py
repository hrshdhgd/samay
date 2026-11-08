"""Turn computed facts into a reading. The template is the default; a local Ollama rewords it
only when OLLAMA_URL is set.

The LLM only rephrases facts we pass in; it must not invent placements or rules.
"""
from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger("samay.narrate")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
TIMEOUT_SECONDS = 20.0

SYSTEM = (
    "You write short, warm daily readings in the Jyotish tradition for a Telegram bot. "
    "Use ONLY the facts provided. Do not invent placements, yogas or events. "
    "Frame everything as traditional interpretation for reflection, not as certain prediction. "
    "Max 120 words. Plain text, no markdown."
)

_client: httpx.AsyncClient | None = None


def enabled() -> bool:
    return bool(OLLAMA_URL)


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


async def narrate(facts: list[str], client: httpx.AsyncClient | None = None) -> str:
    """Reworded facts, or the plain template when narration is off or the model is unavailable."""
    if not enabled():
        return template(facts)
    prompt = "Facts:\n" + "\n".join(f"- {f}" for f in facts) + "\n\nWrite today's reading."
    try:
        r = await (client or _get_client()).post(
            f"{OLLAMA_URL.rstrip('/')}/api/generate",
            json={"model": OLLAMA_MODEL, "system": SYSTEM, "prompt": prompt, "stream": False},
        )
        r.raise_for_status()
        return r.json().get("response", "").strip() or template(facts)
    except (httpx.HTTPError, ValueError) as e:  # a reading must never fail because the LLM is down
        log.warning("narration failed, using template: %s", type(e).__name__)
        return template(facts)
