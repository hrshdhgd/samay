"""Turn computed facts into a reading. Template by default; local Ollama if OLLAMA_URL is set.

The LLM only rephrases facts we pass in; it must not invent placements or rules.
"""
from __future__ import annotations

import os

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")

SYSTEM = (
    "You write short, warm daily readings in the Jyotish tradition for a Telegram bot. "
    "Use ONLY the facts provided. Do not invent placements, yogas or events. "
    "Frame everything as traditional interpretation for reflection, not as certain prediction. "
    "Max 120 words. Plain text, no markdown."
)


def template(facts: list[str]) -> str:
    return "\n".join(f"• {f}" for f in facts)


async def narrate(facts: list[str]) -> str:
    if not OLLAMA_URL:
        return template(facts)
    prompt = "Facts:\n" + "\n".join(f"- {f}" for f in facts) + "\n\nWrite today's reading."
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{OLLAMA_URL.rstrip('/')}/api/generate",
                json={"model": OLLAMA_MODEL, "system": SYSTEM, "prompt": prompt, "stream": False},
            )
            r.raise_for_status()
            text = r.json().get("response", "").strip()
            return text or template(facts)
    except Exception:  # noqa: BLE001 — never fail a reading because the LLM is down
        return template(facts)
