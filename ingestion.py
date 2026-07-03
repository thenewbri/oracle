# Reads signals from Pelosi and Wolf Supabase projects and returns a ranked ticker list

import re
import sys
from datetime import datetime, timezone, timedelta

import anthropic
from supabase import create_client

import config

_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")

_MODEL = "claude-opus-4-5"


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def get_wolf_signals(limit: int = 50) -> list[dict]:
    try:
        client = create_client(config.WOLF_SUPABASE_URL, config.WOLF_SUPABASE_KEY)
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        response = (
            client.table("signals")
            .select("*")
            .gte("created_at", cutoff)
            .not_.is_("transaction_value", "null")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data or []
    except Exception as e:
        print(f"get_wolf_signals() failed: {e}", file=sys.stderr)
        return []


def score_wolf_signal(signal: dict) -> float:
    transaction_value = signal.get("transaction_value")
    trade_pct_of_position = signal.get("trade_pct_of_position")

    if transaction_value is None and trade_pct_of_position is None:
        return 0.0

    dollar_score = 0.0
    if transaction_value is not None:
        if transaction_value >= 5_000_000:
            dollar_score = 1.0
        elif transaction_value >= 2_000_000:
            dollar_score = 0.75
        elif transaction_value >= config.PELOSI_MIN_TRADE_SIZE:
            dollar_score = 0.5

    position_score = 0.0
    if trade_pct_of_position is not None:
        if trade_pct_of_position >= 40.0:
            position_score = 1.0
        elif trade_pct_of_position >= 25.0:
            position_score = 0.75
        elif trade_pct_of_position >= config.WOLF_MIN_POSITION_PCT:
            position_score = 0.5

    score = max(dollar_score, position_score)

    composite_score = signal.get("composite_score")
    if composite_score is not None:
        score *= min(1.0, composite_score / 100)

    return score


def get_pelosi_signals(limit: int = 20) -> list[dict]:
    try:
        client = create_client(config.PELOSI_SUPABASE_URL, config.PELOSI_SUPABASE_KEY)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        today = datetime.now(timezone.utc).date().isoformat()
        response = (
            client.table("signals")
            .select("*")
            .gte("created_at", cutoff)
            .or_(f"watch_end_date.gte.{today},watch_end_date.is.null")
            .not_.is_("direction", "null")
            .order("confidence_score", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data or []
    except Exception as e:
        print(f"get_pelosi_signals() failed: {e}", file=sys.stderr)
        return []


def get_pelosi_tickers_for_sector(sector: str, etf_signal: str) -> list[str]:
    try:
        response = _client().messages.create(
            model=_MODEL,
            max_tokens=500,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Search for the most liquid and vulnerable individual stocks in the {sector} sector "
                        "right now that would be good PUT candidates given current market conditions. "
                        f"The ETF proxy for this sector is {etf_signal}. Return only the top 5 ticker symbols, "
                        "one per line, no explanation, no commentary."
                    ),
                }
            ],
        )
        text_blocks = [block.text for block in response.content if hasattr(block, "text")]
        full_text = "\n".join(text_blocks)
        candidates = [line.strip().upper().lstrip("-*0123456789. ") for line in full_text.splitlines()]
        tickers = [c for c in candidates if _TICKER_RE.match(c)]
        return tickers[:5]
    except Exception as e:
        print(f"get_pelosi_tickers_for_sector({sector}) failed: {e}", file=sys.stderr)
        return []


def score_pelosi_signal(signal: dict) -> float:
    confidence_score = signal.get("confidence_score")
    if confidence_score is None:
        return 0.0
    if confidence_score >= 0.8:
        return 1.0
    if confidence_score >= 0.6:
        return 0.75
    if confidence_score >= 0.4:
        return 0.5
    return 0.0


def get_ranked_tickers() -> list[str]:
    scores: dict[str, float] = {}

    wolf_signals = get_wolf_signals()
    for signal in wolf_signals:
        ticker = signal.get("ticker")
        if not ticker:
            continue
        score = score_wolf_signal(signal)
        if score <= 0.0:
            continue
        scores[ticker] = max(scores.get(ticker, 0.0), score)

    pelosi_signals = get_pelosi_signals()
    for signal in pelosi_signals:
        score = score_pelosi_signal(signal)
        if score <= 0.0:
            continue
        sector = signal.get("sector")
        etf_signal = signal.get("etf_signal")
        if not sector or not etf_signal:
            continue
        for ticker in get_pelosi_tickers_for_sector(sector, etf_signal):
            scores[ticker] = max(scores.get(ticker, 0.0), score)

    ranked = sorted(scores, key=lambda t: scores[t], reverse=True)
    return ranked[: config.MAX_SIGNAL_COUNT]
