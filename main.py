# Entry point: initializes the scheduler, loads config, and starts the Telegram bot

import asyncio
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import config
import ingestion
import macro
import memory
import research
import synthesis
import telegram_bot


def run_morning_briefing() -> None:
    print(f"[{datetime.now(timezone.utc).isoformat()}] Oracle: starting morning briefing", flush=True)
    try:
        triggered, explanation = macro.check_macro_circuit_breaker()

        if triggered:
            asyncio.new_event_loop().run_until_complete(
                telegram_bot.send_message(
                    f"⚠️ <b>Macro circuit breaker triggered</b>\n\n"
                    f"{explanation}\n\n"
                    f"Running full macro refresh before briefing."
                )
            )

        today_is_monday = datetime.now(timezone.utc).weekday() == 0

        if triggered or today_is_monday:
            macro_context = macro.fetch_macro_context()
        else:
            macro_context = macro.get_macro_context()

        tickers = ingestion.get_ranked_tickers()

        if not tickers:
            asyncio.new_event_loop().run_until_complete(
                telegram_bot.send_message("Oracle: no signals above threshold today.")
            )
            return

        packages = []
        for ticker in tickers:
            package = research.research_ticker(ticker)
            if package is None:
                continue
            market_cap = package["fundamentals"].get("market_cap")
            if market_cap is None or market_cap < config.MIN_MARKET_CAP:
                print(f"[briefing] {ticker} skipped — market cap {market_cap} below threshold", flush=True)
                continue
            packages.append(package)

        if len(packages) < 2:
            asyncio.new_event_loop().run_until_complete(
                telegram_bot.send_message("Oracle: insufficient quality signals today.")
            )
            return

        memory_context = memory.format_memory_for_context()
        synthesis_output = synthesis.synthesise(packages, macro_context, memory_context)
        recommendations = synthesis.parse_recommendations(synthesis_output)

        for rec in recommendations:
            memory.save_recommendation(
                ticker=rec.get("ticker", ""),
                thesis=rec.get("thesis", ""),
                put_details={"recommended_put": rec.get("recommended_put", ""), "conviction": rec.get("conviction", "")},
                source=rec.get("signal_source", ""),
                macro_context=macro_context,
            )

        asyncio.new_event_loop().run_until_complete(
            telegram_bot.send_briefing(synthesis_output, macro_context)
        )

        print(f"[{datetime.now(timezone.utc).isoformat()}] Oracle: morning briefing complete", flush=True)

    except Exception as e:
        print(f"[{datetime.now(timezone.utc).isoformat()}] Oracle: morning briefing error: {e}", file=sys.stderr, flush=True)
        asyncio.new_event_loop().run_until_complete(
            telegram_bot.send_message(f"⚠️ Oracle morning briefing failed: {e}")
        )


def run_sanity_check() -> None:
    if datetime.now(timezone.utc).weekday() == 0:
        return

    triggered, explanation = macro.check_macro_circuit_breaker()

    if triggered:
        asyncio.new_event_loop().run_until_complete(
            telegram_bot.send_message(f"⚠️ <b>Macro alert</b>: {explanation}")
        )


def main() -> None:
    scheduler = BackgroundScheduler(timezone="Europe/London")

    scheduler.add_job(
        run_morning_briefing,
        CronTrigger(hour=7, minute=0, day_of_week="mon-fri"),
    )
    scheduler.add_job(
        run_sanity_check,
        CronTrigger(hour=7, minute=15, day_of_week="tue-fri"),
    )

    scheduler.start()
    print("Oracle scheduler started. Waiting for jobs.", flush=True)

    app = telegram_bot.build_application()

    asyncio.new_event_loop().run_until_complete(
        telegram_bot.send_message("✅ Oracle is online. Send me a ticker like $AAPL or ask me anything.")
    )

    try:
        app.run_polling()
    except KeyboardInterrupt:
        pass
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    main()
