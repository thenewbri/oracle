# Defines Telegram bot handlers for user commands and scheduled message delivery

import asyncio
import base64
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from telegram import Bot, Update
from telegram.ext import Application, ApplicationBuilder, ContextTypes, MessageHandler, filters

import config
import macro
import memory
import research
import synthesis

_MODEL = "claude-opus-4-5"
_MACRO_CACHE = Path(__file__).parent / "macro_cache.txt"


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


# ---------------------------------------------------------------------------
# Outbound messaging
# ---------------------------------------------------------------------------

async def send_message(text: str) -> None:
    try:
        bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
        async with bot:
            if len(text) <= 4000:
                await bot.send_message(
                    chat_id=config.TELEGRAM_CHAT_ID,
                    text=text,
                    parse_mode="HTML",
                )
            else:
                chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
                for chunk in chunks:
                    await bot.send_message(
                        chat_id=config.TELEGRAM_CHAT_ID,
                        text=chunk,
                        parse_mode="HTML",
                    )
    except Exception as e:
        print(f"send_message() failed: {e}", file=sys.stderr)


async def send_briefing(recommendations_text: str, macro_summary: str) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    macro_preview = macro_summary[:300] + "..." if len(macro_summary) > 300 else macro_summary
    message = (
        f"🔍 <b>Oracle Morning Briefing</b> — {today}\n\n"
        f"<b>Macro:</b> {macro_preview}\n\n"
        f"{recommendations_text}"
    )
    await send_message(message)


# ---------------------------------------------------------------------------
# Incoming message handlers
# ---------------------------------------------------------------------------

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""

    if text.startswith("$"):
        ticker = text[1:].strip().upper()
        await handle_ticker_query(ticker, update, context)
    elif "refresh macro" in text.lower():
        if _MACRO_CACHE.exists():
            _MACRO_CACHE.unlink()
        await update.message.reply_text("Macro cache cleared — will fetch fresh on next run.")
    elif "macro" in text.lower():
        await handle_macro_query(update, context)
    else:
        await handle_general_query(text, update, context)


async def handle_ticker_query(ticker: str, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"🔍 Researching {ticker}...")

    package = await asyncio.to_thread(research.research_ticker, ticker)

    if package is None:
        await update.message.reply_text(
            f"Could not research {ticker} — either below $5B market cap, "
            "no liquid puts, or data unavailable."
        )
        return

    macro_context = await asyncio.to_thread(macro.get_macro_context)
    memory_context = memory.format_memory_for_context()

    result = await asyncio.to_thread(synthesis.synthesise, [package], macro_context, memory_context)
    await send_message(result)


async def handle_macro_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    macro_context = await asyncio.to_thread(macro.get_macro_context)
    if len(macro_context) > 3000:
        macro_context = macro_context[:3000] + "... [truncated]"
    await send_message(macro_context)


async def handle_general_query(message_text: str, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🤔 Thinking...")

    system_prompt = (
        "You are Oracle, a PUT options trading analyst assistant. Answer questions about trades, "
        "markets, and recommendations concisely. You have access to recent recommendation history "
        "provided below.\n\n"
        + memory.format_memory_for_context()
    )

    response = await asyncio.to_thread(
        lambda: _client().messages.create(
            model=_MODEL,
            max_tokens=1000,
            system=system_prompt,
            messages=[{"role": "user", "content": message_text}],
        )
    )

    text_blocks = [block.text for block in response.content if hasattr(block, "text")]
    await send_message("\n".join(text_blocks).strip())


async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📸 Got your screenshot — analysing...")

    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()

    image_data = base64.standard_b64encode(photo_bytes).decode("utf-8")

    response = await asyncio.to_thread(
        lambda: _client().messages.create(
            model=_MODEL,
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Extract any stock tickers, company names, or trade signals from this image. "
                                "Return only a plain list, one item per line."
                            ),
                        },
                    ],
                }
            ],
        )
    )

    text_blocks = [block.text for block in response.content if hasattr(block, "text")]
    response_text = "\n".join(text_blocks)

    STOPWORDS = {
        "A", "I", "IN", "OF", "OR", "AT", "TO", "BE", "IS", "IT", "ON", "NO", "SO", "DO", "GO",
        "BY", "MY", "AN", "AS", "WE", "HE", "ME", "US", "UP", "AM", "PM", "THE", "AND", "FOR",
        "NOT", "BUT", "PUT", "ARE", "WAS", "HAS", "HAD", "DID", "GET", "GOT", "NEW", "NOW",
        "IV", "OI", "ETF", "CEO", "CFO", "IPO", "SEC", "USD", "YTD", "EPS", "PE",
    }
    tickers = list(dict.fromkeys(
        t for t in re.findall(r"\b[A-Z]{1,5}\b", response_text)
        if t not in STOPWORDS
    ))

    if not tickers:
        await update.message.reply_text("Could not identify any tickers in that image.")
        return

    for ticker in tickers[:3]:
        await handle_ticker_query(ticker, update, context)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def build_application() -> Application:
    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))
    return app
