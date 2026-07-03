# Tracks and interprets macroeconomic indicators (rates, inflation, GDP, etc.)

from datetime import datetime, timezone, timedelta
from pathlib import Path

import anthropic

import config

_CACHE_FILE = Path(__file__).parent / "macro_cache.txt"
_MODEL = "claude-opus-4-5"
_WEB_SEARCH_TOOL = [{"type": "web_search_20250305", "name": "web_search"}]
_SYSTEM_PROMPT = (
    "You are a macro research analyst. Search the web for current information and return a "
    "structured summary of macro conditions relevant to PUT options trading. Cover: Fed stance "
    "and rate expectations, US trade war and tariff developments, geopolitical risks (Middle East, "
    "China), energy supply picture, and any major sector-specific stress. Be specific and current. "
    "Return plain text, no markdown."
)


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def fetch_macro_context() -> str:
    today = datetime.now(timezone.utc).strftime("%B %d %Y")
    response = _client().messages.create(
        model=_MODEL,
        max_tokens=1500,
        system=_SYSTEM_PROMPT,
        tools=_WEB_SEARCH_TOOL,
        messages=[
            {"role": "user", "content": f"Give me a current macro briefing for PUT options trading. Today is {today}."}
        ],
    )
    text_blocks = [block.text for block in response.content if hasattr(block, "text")]
    return "\n".join(text_blocks).strip()


def get_macro_context() -> str:
    if _CACHE_FILE.exists():
        lines = _CACHE_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
        if lines:
            try:
                cached_at = datetime.fromisoformat(lines[0].strip())
                if datetime.now(timezone.utc) - cached_at < timedelta(days=7):
                    return "".join(lines[1:]).strip()
            except ValueError:
                pass

    result = fetch_macro_context()
    timestamp = datetime.now(timezone.utc).isoformat()
    _CACHE_FILE.write_text(f"{timestamp}\n{result}", encoding="utf-8")
    return result


def check_macro_circuit_breaker() -> tuple[bool, str]:
    response = _client().messages.create(
        model=_MODEL,
        max_tokens=200,
        system="You are a macro risk monitor. Search the web for breaking financial and geopolitical news. Be terse and precise.",
        tools=_WEB_SEARCH_TOOL,
        messages=[
            {
                "role": "user",
                "content": (
                    "Has there been any major unexpected macro event in the last 24 hours that would "
                    "significantly affect US stock PUT options? Examples: surprise Fed decision, major "
                    "geopolitical escalation, large unexpected economic data release. Answer with only "
                    "YES or NO on the first line, then one sentence explanation."
                ),
            }
        ],
    )
    text_blocks = [block.text for block in response.content if hasattr(block, "text")]
    full_text = "\n".join(text_blocks).strip()

    lines = [line.strip() for line in full_text.splitlines() if line.strip()]
    triggered = lines[0].upper().startswith("YES") if lines else False
    explanation = lines[1] if len(lines) > 1 else full_text

    return triggered, explanation
