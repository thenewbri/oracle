# Combines research and macro signals into a unified market outlook or trade thesis

from datetime import datetime, timezone

import anthropic

import config

_MODEL = "claude-opus-4-5"


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def _build_system_prompt(macro_context: str, memory_context: str) -> str:
    identity = (
        "You are Oracle, a PUT options trading analyst. You work exclusively for one trader. "
        "You never recommend calls. You never recommend more than 3 trades. "
        "You are precise, blunt, and correct."
    )

    rules = (
        "RULES:\n"
        "- Default to PUT recommendations. This is primarily a bearish signal service.\n"
        "- Exception: when a signal represents a large concentrated BUY by a high-conviction insider (single stock, significant size, not diversified), evaluate the long side. If the long thesis is strong, recommend it — note both the call option AND the stock as execution alternatives and let the trader decide.\n"
        "- The bar for a long recommendation is higher than for a put. It needs a specific catalyst thesis, not just insider activity alone.\n"
        "- Only recommend trades with liquid options: open interest > 500, bid-ask spread < 10% of premium.\n"
        "- Minimum market cap $5B.\n"
        "- Maximum 3 recommendations per session.\n"
        "- If fewer than 2 strong setups exist, recommend fewer. Do not pad with weak trades.\n"
        "- DTE: match to conviction. High conviction = shorter dated. Lower conviction = longer dated.\n"
        "- Minimum DTE is 7 days. Never recommend a put expiring in less than 7 days — there is not enough time to be right.\n"
        "- Always state the specific strike and expiry you recommend, not a range."
    )

    sector_context = (
        "SECTOR PRIORITIES:\n"
        "High: consumer discretionary, retail, airlines, biotech, pharma, semiconductors\n"
        "Medium: financials, real estate\n"
        "Watchlist (higher bar): defence, aerospace\n"
        "Deprioritise: energy, utilities"
    )

    macro = (
        f"CURRENT MACRO CONTEXT (fetched {datetime.now(timezone.utc).strftime('%Y-%m-%d')}):\n"
        f"{macro_context}"
    )

    memory = f"YOUR RECENT RECOMMENDATIONS (last 7 days):\n{memory_context}"

    output_format = (
        "OUTPUT FORMAT: For each recommendation return exactly this structure:\n"
        "TICKER: [symbol]\n"
        "THESIS: [2-3 sentences on why this is a PUT setup right now]\n"
        "SIGNAL SOURCE: [Pelosi / Wolf / Both]\n"
        "RECOMMENDED PUT: [strike] strike, [expiry] expiry, [DTE] DTE\n"
        "CONVICTION: [High / Medium] — [one sentence reason]\n"
        "RISK: [one sentence on what would invalidate this trade]\n"
        "DIRECTION: [LONG / SHORT] — include this field on every recommendation so the trader knows immediately which way the trade goes.\n\n"
        "Separate each recommendation with ---"
    )

    return "\n\n".join([identity, rules, sector_context, macro, memory, output_format])


def synthesise(research_packages: list[dict], macro_context: str, memory_context: str) -> str:
    ticker_blocks = []

    for package in research_packages:
        f = package["fundamentals"]
        opts = package["options"]
        news = package["news"]

        top_puts = opts["puts"][:5]
        puts_lines = []
        for p in top_puts:
            iv = p["implied_volatility"] or 0
            puts_lines.append(
                f"  {p['expiry']} ${p['strike']}p"
                f" — IV: {iv:.0%}"
                f" | OI: {p['open_interest']}"
                f" | Bid: ${p['bid']} Ask: ${p['ask']}"
            )
        puts_formatted = "\n".join(puts_lines)

        news_formatted = "\n".join(f"  {line}" for line in news)

        block = (
            f"TICKER: {f['symbol']}\n"
            f"SECTOR: {f['sector']}\n"
            f"MARKET CAP: ${f['market_cap']:,.0f}\n"
            f"CURRENT PRICE: ${f['current_price']}\n"
            f"52W HIGH: ${f['fifty_two_week_high']} | 52W LOW: ${f['fifty_two_week_low']}\n"
            f"PE: {f['pe_ratio']} | FORWARD PE: {f['forward_pe']}\n"
            f"SHORT RATIO: {f['short_ratio']}\n"
            f"ANALYST TARGET: ${f['analyst_target_price']}\n"
            f"EARNINGS DATE: {f['earnings_date']}\n"
            f"\nTOP PUTS AVAILABLE:\n{puts_formatted}\n"
            f"\nRECENT NEWS:\n{news_formatted}"
        )
        ticker_blocks.append(block)

    user_message = "\n\n---\n\n".join(ticker_blocks)

    response = _client().messages.create(
        model=_MODEL,
        max_tokens=2000,
        system=_build_system_prompt(macro_context, memory_context),
        messages=[{"role": "user", "content": user_message}],
    )

    text_blocks = [block.text for block in response.content if hasattr(block, "text")]
    return "\n".join(text_blocks).strip()


def parse_recommendations(synthesis_output: str) -> list[dict]:
    recommendations = []

    for block in synthesis_output.split("---"):
        block = block.strip()
        if not block or "TICKER:" not in block:
            continue

        fields = {
            "ticker": "",
            "thesis": "",
            "signal_source": "",
            "recommended_put": "",
            "conviction": "",
            "risk": "",
        }

        key_map = {
            "TICKER:": "ticker",
            "THESIS:": "thesis",
            "SIGNAL SOURCE:": "signal_source",
            "RECOMMENDED PUT:": "recommended_put",
            "CONVICTION:": "conviction",
            "RISK:": "risk",
        }

        lines = block.splitlines()
        current_key = None

        for line in lines:
            matched = False
            for prefix, field in key_map.items():
                if line.startswith(prefix):
                    fields[field] = line[len(prefix):].strip()
                    current_key = field
                    matched = True
                    break
            # Append continuation lines to the current field (e.g. multi-line THESIS)
            if not matched and current_key and line.strip():
                fields[current_key] += " " + line.strip()

        recommendations.append(fields)

    return recommendations
