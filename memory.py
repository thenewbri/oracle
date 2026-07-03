# Reads and writes persistent state (past analyses, positions, alerts) via Supabase

import json
import sys
from datetime import datetime, timezone, timedelta

from supabase import create_client

import config

_TABLE = "oracle_recommendations"


def _get_client():
    return create_client(config.ORACLE_SUPABASE_URL, config.ORACLE_SUPABASE_KEY)


def save_recommendation(
    ticker: str,
    thesis: str,
    put_details: dict,
    source: str,
    macro_context: str,
) -> None:
    try:
        _get_client().table(_TABLE).insert({
            "ticker": ticker,
            "thesis": thesis,
            "put_details": json.dumps(put_details),
            "source": source,
            "macro_context": macro_context,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        print(f"save_recommendation({ticker}) failed: {e}", file=sys.stderr)


def get_recent_recommendations(days: int = 7) -> list[dict]:
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        response = (
            _get_client()
            .table(_TABLE)
            .select("*")
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .execute()
        )
        return response.data or []
    except Exception as e:
        print(f"get_recent_recommendations() failed: {e}", file=sys.stderr)
        return []


def format_memory_for_context(days: int = 7) -> str:
    recommendations = get_recent_recommendations(days=days)
    if not recommendations:
        return "No recent recommendations."

    lines = []
    for rec in recommendations:
        date = rec.get("created_at", "")[:10]
        ticker = rec.get("ticker", "")
        thesis = rec.get("thesis", "")
        put_details = rec.get("put_details", "")
        lines.append(f"[{date}] {ticker}: {thesis} | PUT: {put_details}")

    return "\n".join(lines)
