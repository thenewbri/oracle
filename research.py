# Gathers raw data for a ticker: fundamentals, options snapshot, and recent news

import sys

import anthropic
import yfinance as yf

import config

_MODEL = "claude-opus-4-5"
_WEB_SEARCH_TOOL = [{"type": "web_search_20250305", "name": "web_search"}]


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def get_price_and_fundamentals(ticker: str) -> dict | None:
    info = yf.Ticker(ticker).info

    market_cap = info.get("marketCap")
    if market_cap is None or market_cap < config.MIN_MARKET_CAP:
        return None

    return {
        "symbol": info.get("symbol"),
        "company_name": info.get("longName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "market_cap": market_cap,
        "current_price": info.get("currentPrice"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        "pe_ratio": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_date": info.get("earningsTimestamp"),
        "analyst_target_price": info.get("targetMeanPrice"),
        "short_ratio": info.get("shortRatio"),
    }


def get_options_snapshot(ticker: str, max_expiries: int = 3) -> dict | None:
    t = yf.Ticker(ticker)
    expiration_dates = t.options[:max_expiries]

    all_puts = []
    for expiry in expiration_dates:
        chain = t.option_chain(expiry)
        puts = chain.puts.copy()
        puts = puts[puts["openInterest"] >= config.MIN_OPEN_INTEREST]

        for _, row in puts.iterrows():
            all_puts.append({
                "expiry": expiry,
                "strike": row.get("strike"),
                "bid": row.get("bid"),
                "ask": row.get("ask"),
                "implied_volatility": row.get("impliedVolatility"),
                "open_interest": row.get("openInterest"),
                "volume": row.get("volume"),
                "last_price": row.get("lastPrice"),
            })

    if not all_puts:
        return None

    all_puts.sort(key=lambda x: x["open_interest"] or 0, reverse=True)

    return {
        "expiries": list(expiration_dates),
        "puts": all_puts,
    }


def get_recent_news(ticker: str, company_name: str) -> list[str]:
    response = _client().messages.create(
        model=_MODEL,
        max_tokens=600,
        system=(
            "You are a financial news researcher. Search for recent news about the company provided. "
            "Return only a plain text list of the 5 most relevant recent headlines or developments, "
            "one per line, with their dates. No markdown, no commentary."
        ),
        tools=_WEB_SEARCH_TOOL,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Find the 5 most important recent news items about {company_name} ({ticker}) "
                    "in the last 30 days that could affect the stock price negatively."
                ),
            }
        ],
    )
    text_blocks = [block.text for block in response.content if hasattr(block, "text")]
    full_text = "\n".join(text_blocks)
    return [line for line in full_text.splitlines() if line.strip()]


def research_ticker(ticker: str) -> dict | None:
    try:
        fundamentals = get_price_and_fundamentals(ticker)
        if fundamentals is None:
            return None

        options = get_options_snapshot(ticker)
        if options is None:
            return None

        news = get_recent_news(ticker, fundamentals["company_name"] or ticker)

        return {
            "fundamentals": fundamentals,
            "options": options,
            "news": news,
        }
    except Exception as e:
        print(f"research_ticker({ticker}) failed: {e}", file=sys.stderr)
        return None
