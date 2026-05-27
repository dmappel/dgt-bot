#!/usr/bin/env python3
"""
DGT Cita Previa Availability Bot

Checks for available appointment slots at DGT Barcelona for
"Canjes de permisos de conduccion" on a recurring schedule.

Usage:
    python bot.py
"""

import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

import config
import alerts
import automation

CET = ZoneInfo("Europe/Madrid")


def is_within_operating_hours() -> bool:
    now = datetime.now(CET)
    return config.START_HOUR <= now.hour < config.END_HOUR


def format_time() -> str:
    return datetime.now(CET).strftime("%H:%M:%S CET")


def run_bot():
    print("=" * 60)
    print("  DGT Cita Previa Availability Bot")
    print(f"  Centro: {config.CENTRO}")
    print(f"  Check interval: every {config.CHECK_INTERVAL_MINUTES} min")
    print(f"  Active hours: {config.START_HOUR}:00 - {config.END_HOUR}:00 CET")
    print("=" * 60)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = None
        page = None

        def fresh_context():
            """Create a clean browser context (clears all cookies/session)."""
            nonlocal context, page
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="es-ES",
            )
            page = context.new_page()
            print(f"    [Fresh browser context created]")
            return page

        page = fresh_context()
        session_authenticated = False
        checks_done = 0

        try:
            while True:
                if not is_within_operating_hours():
                    now = datetime.now(CET)
                    print(
                        f"\n[{format_time()}] Outside operating hours "
                        f"({config.START_HOUR}:00-{config.END_HOUR}:00). "
                        f"Sleeping until next window..."
                    )
                    wake = now.replace(
                        hour=config.START_HOUR, minute=0, second=0, microsecond=0
                    )
                    if now.hour >= config.END_HOUR:
                        from datetime import timedelta
                        wake += timedelta(days=1)
                    sleep_seconds = max(60, (wake - now).total_seconds())
                    print(f"    Will resume at ~{wake.strftime('%H:%M CET')}")
                    time.sleep(sleep_seconds)
                    continue

                checks_done += 1
                print(
                    f"\n{'='*60}\n"
                    f"[{format_time()}] Check #{checks_done}\n"
                    f"{'='*60}"
                )

                if session_authenticated and automation.is_session_valid(page):
                    result = automation.run_recheck(page)
                else:
                    session_authenticated = False
                    result = automation.run_full_flow(page)

                if result is True:
                    alerts.alert_cita_found()
                    print(f"[{format_time()}] User took over. Bot pausing.")
                    print("Press Enter to resume checking, or Ctrl+C to exit.")
                    input()
                    session_authenticated = False
                    continue

                if result is False:
                    session_authenticated = True
                    print(
                        f"\n[{format_time()}] No citas. "
                        f"Next check in {config.CHECK_INTERVAL_MINUTES} minutes."
                    )
                    time.sleep(config.CHECK_INTERVAL_MINUTES * 60)

                if result is None:
                    session_authenticated = False
                    print(
                        f"\n[{format_time()}] Flow failed. "
                        f"Creating fresh session and retrying in 1 minute..."
                    )
                    page = fresh_context()
                    time.sleep(60)

        except KeyboardInterrupt:
            print(f"\n[{format_time()}] Bot stopped by user.")
        finally:
            print("Closing browser...")
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            try:
                browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    run_bot()
