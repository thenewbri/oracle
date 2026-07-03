# Oracle — Claude Code Reference

## What this project does

Oracle is a personal PUT options trading assistant. It runs as a persistent process that:
- Pulls insider trading signals from two external Supabase databases (Pelosi and Wolf)
- Scores and ranks tickers by signal size/conviction
- Researches each ticker using yfinance (fundamentals, options chain) and Claude with web search (news)
- Synthesises all data into 1-3 trade recommendations using Claude claude-opus-4-5
- Delivers a morning briefing at 07:00 Europe/London via Telegram, Monday–Friday
- Responds to ad-hoc queries over Telegram in real time

It is a single-user tool. There is no API, no web interface, no auth layer.

## Tech stack

- **Python 3.11** managed by `uv`
- **Anthropic API** (`claude-opus-4-5`) — synthesis, macro fetch, news research, circuit breaker, general chat, vision
- **Web search tool** (`web_search_20250305`) — used in `macro.py` and `research.py`, NOT in `synthesis.py`
- **yfinance** — fundamentals and options chain data
- **python-telegram-bot v22** — async bot with `run_polling()`
- **APScheduler** (`BackgroundScheduler`) — runs scheduled jobs on a background thread while the Telegram bot blocks the main thread
- **Supabase** — three separate projects: Pelosi signals, Wolf signals, Oracle memory
- **python-dotenv** — loads `.env` at import time in `config.py`

## How to run locally

```bash
# Install uv if not present
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies (creates .venv automatically)
~/.local/bin/uv sync

# Set up credentials
cp .env.example .env
# Edit .env and fill in all 9 variables

# Run the bot
~/.local/bin/uv run python main.py
```

On startup, Oracle sends "✅ Oracle is online..." to Telegram, then blocks on `run_polling()`. Kill with Ctrl-C — the scheduler shuts down cleanly via `finally`.

## One-time Supabase setup

Run `setup.sql` in the Oracle Supabase project (SQL editor in the dashboard) before first run. This creates the `oracle_recommendations` table. Pelosi and Wolf Supabase projects are external — Oracle only reads from them, never writes.

## Environment variables

All 9 are required. Missing any one causes a `KeyError` at import time (intentional — fail loud):

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | All Claude API calls |
| `TELEGRAM_BOT_TOKEN` | Bot identity |
| `TELEGRAM_CHAT_ID` | The single chat Oracle messages |
| `PELOSI_SUPABASE_URL` / `PELOSI_SUPABASE_KEY` | Pelosi signals database (read-only) |
| `WOLF_SUPABASE_URL` / `WOLF_SUPABASE_KEY` | Wolf signals database (read-only) |
| `ORACLE_SUPABASE_URL` / `ORACLE_SUPABASE_KEY` | Oracle's own memory database |

## Key files

| File | What it does |
|---|---|
| `main.py` | Entry point. Owns the scheduler and starts the bot. Contains `run_morning_briefing()` and `run_sanity_check()`. |
| `config.py` | Loads `.env`, exposes all constants. Import this everywhere — never call `os.environ` directly in other modules. |
| `ingestion.py` | Reads Pelosi and Wolf Supabase tables, scores signals, returns a ranked list of up to 15 tickers. |
| `research.py` | Given a ticker, fetches fundamentals + options chain (yfinance) and recent news (Claude + web search). Returns a package dict or None if the ticker fails filters. |
| `macro.py` | Fetches a weekly macro briefing via Claude + web search. Caches to `macro_cache.txt`. Also runs a daily circuit breaker check. |
| `synthesis.py` | Takes research packages + macro context, calls Claude (no web search), returns structured recommendation text. Also parses that text back into dicts. |
| `memory.py` | Reads and writes `oracle_recommendations` in the Oracle Supabase project. Formats past recommendations as a string for injection into Claude's context. |
| `telegram_bot.py` | All Telegram I/O. Handles `$TICKER` queries, macro queries, photo analysis, and free-text chat. `build_application()` returns a configured PTB `Application` — does not start it. |
| `setup.sql` | One-time DDL for the Oracle Supabase project. Run once, never again. |
| `macro_cache.txt` | Auto-generated. First line is a UTC ISO timestamp, rest is the macro briefing. Valid for 7 days. Delete it or send "refresh macro" to Telegram to force a fresh fetch. |

## Filters and thresholds (all in config.py)

- `MIN_MARKET_CAP = 5_000_000_000` — tickers below $5B are dropped in `research.py`
- `MIN_OPEN_INTEREST = 500` — puts below this OI are excluded from the options snapshot
- `MAX_SIGNAL_COUNT = 15` — maximum tickers passed to research each morning
- `PELOSI_MIN_TRADE_SIZE = 1_000_000` — Pelosi trades below $1M score 0.0 and are dropped
- `WOLF_MIN_POSITION_PCT = 15.0` — Wolf positions below 15% score 0.0 and are dropped
- `BRIEFING_HOUR = 7` — used in scheduler cron config (Europe/London)

## Schema TODOs

`ingestion.py` has four `# SCHEMA TODO` comments marking placeholder column names that need confirming against the real Pelosi and Wolf Supabase tables:
- Table name: `signals` (assumed)
- Columns assumed: `created_at`, `ticker`, `trade_value` (Pelosi), `position_pct` (Wolf)

Until these are confirmed, `get_ranked_tickers()` will return an empty list and Oracle will send "no signals above threshold today" every morning.

## Scheduling

- **07:00 Mon–Fri (Europe/London)**: `run_morning_briefing()` — full pipeline
- **07:15 Tue–Fri (Europe/London)**: `run_sanity_check()` — circuit breaker only, skips Monday

The scheduler runs on a background thread. All `send_message()` calls from scheduled jobs use `asyncio.new_event_loop().run_until_complete()` because the main thread's event loop is owned by PTB's `run_polling()`.

## Telegram commands

Send these to the bot directly:

| Input | Response |
|---|---|
| `$AAPL` | Full research + synthesis on AAPL |
| `macro` | Current cached macro context (truncated to 3000 chars) |
| `refresh macro` | Deletes `macro_cache.txt`, confirms — next fetch will be live |
| Any photo | Vision analysis → ticker extraction → research on up to 3 tickers |
| Anything else | General Claude chat with memory context injected |

## Claude model usage

Every Claude call uses `claude-opus-4-5`. This is explicit in each module (`_MODEL = "claude-opus-4-5"`). Do not change to a different model without testing — the structured output parsing in `parse_recommendations()` depends on Claude following the exact output format specified in the system prompt.

## What NOT to do

- **Do not add `os.environ` calls outside `config.py`** — all env access goes through config constants.
- **Do not add web search tools to `synthesis.py`** — synthesis is pure reasoning over pre-fetched data. Web search belongs only in `macro.py` and `research.py`.
- **Do not recommend puts with DTE < 7** — this rule is enforced in the synthesis prompt. Do not remove it.
- **Do not change `asyncio.new_event_loop()` back to `asyncio.get_event_loop()`** in `main.py` — the scheduler runs on background threads that don't have a running event loop; `get_event_loop()` is deprecated for this usage in Python 3.10+.
- **Do not start the Telegram application inside `build_application()`** — it returns the app unconfigured; `main()` is responsible for calling `run_polling()`.
- **Do not commit `.env`** — it is not in `.gitignore` yet, so be careful.

## Code style

- Flat module structure — no packages, no subdirectories, everything imports each other directly.
- No classes. All modules expose plain functions.
- `_client()` factory pattern in every module that calls the Anthropic API — instantiated per-call, not at module level.
- Errors are logged to `stderr` with `print(..., file=sys.stderr)` and swallowed — callers receive `None` or `[]`. The bot sends a Telegram message on critical failures.
- Type hints on all function signatures. No docstrings.
- No comments except where genuinely non-obvious (the `# SCHEMA TODO` markers are the main exception).
- All timestamps are UTC. `datetime.now(timezone.utc)` everywhere — no naive datetimes.
- Blocking I/O inside async Telegram handlers is wrapped with `asyncio.to_thread()`.
