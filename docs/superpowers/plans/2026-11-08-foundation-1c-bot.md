# Foundation 1C — Telegram Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A guided, button-first Telegram bot for non-technical relatives, built on the service layer,
with an allowlist, persisted drafts and no birth data in logs.

**Architecture:** `bot/flow.py` is a pure state machine (draft + text/button in, draft + reply out;
no Telegram imports) so every conversational path is unit-tested. `bot/app.py` is a thin PTB adapter
that loads/saves drafts in `store.py` and runs sync work with `asyncio.to_thread`. Wording lives in
`render/prompts.py`. The flow is a custom state machine rather than PTB's `ConversationHandler`
because its state must survive restarts through the store.

**Tech stack:** python-telegram-bot 21, SQLite (stdlib), httpx.

---

### Task 1: Friendlier input parsing
**Files:** modify `samay/service.py`, `tests/test_service.py`.
- [ ] `parse_date`: accept `15-08-1952`, `15/8/1952`, `15.08.1952`, `1952-08-15`, `15 August 1952`,
  `15th Aug 1952`, `August 15, 1952`. `parse_clock`: `6:30`, `6.30`, `6pm`, `6:30 PM`, `18:30`;
  returns hour, minute and whether AM/PM is unknown. `parse_local` keeps 24-hour semantics.
- [ ] Commit.

### Task 2: Store
**Files:** create `samay/store.py`; test `tests/test_store.py`.
- [ ] `users` (raw `BirthInput` fields) and `drafts` (JSON, `updated_at`), versioned with
  `PRAGMA user_version` migrations. Drafts expire after 30 minutes and are deleted on read and by
  `purge_expired`. `/forget` removes both rows.
- [ ] Commit.

### Task 3: Prompts and flow
**Files:** create `samay/render/prompts.py`, `samay/bot/__init__.py`, `samay/bot/flow.py`;
test `tests/test_flow.py`.
- [ ] Steps: date → time (→ AM/PM buttons) → place (→ nearby town if not found, or place buttons)
  → DST fold buttons if needed → done. Every button carries a step token; stale taps get a friendly
  restart; text where a button is expected re-asks; every reply offers Start over.
- [ ] Commit.

### Task 4: Narration
**Files:** modify `samay/narrate.py`, `samay/render/text.py`; test `tests/test_narrate.py`.
- [ ] Off unless `OLLAMA_URL` is set; one shared client; `llama3.2:3b`; 20 s timeout; any failure →
  template. `today_facts` supplies the facts.
- [ ] Commit.

### Task 5: Bot adapter and entry point
**Files:** create `samay/bot/app.py`, `samay/bot/__main__.py`; test `tests/test_bot.py`.
- [ ] Allowlist guard on every handler (silent for others); refuse to start with an empty list;
  commands `/start /help /birth /chart /dasha /today /forget` plus a permanent menu keyboard;
  forget asks for confirmation; error handler logs chat id and error type only; `httpx`/`telegram`
  loggers at WARNING; `allowed_updates=[MESSAGE, CALLBACK_QUERY]`; `warm()` on startup.
- [ ] Commit.
