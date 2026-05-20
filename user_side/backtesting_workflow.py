from libb import LIBBmodel
from .prompt_orchestration.prompt_models import (
    prompt_daily_report,
    prompt_deep_research,
)
from libb.other.parse import parse_json
import json
import pandas as pd
import threading
import time
from pathlib import Path

MODELS = ["groq", "openrouter", "gemini"]

STARTING_CASH_DEFAULT   = 1_000.0
COMMISSION_DEFAULT      = 1.0
MARKET_CALENDAR_DEFAULT = "NYSE"

# Wie viele Tage historische Daten für Backtests geladen werden.
HISTORY_WINDOW_DAYS = 14

def weekly_flow(date):
    for model in MODELS:
        libb = LIBBmodel(f"user_side/runs/run_v1/{model}", run_date=date)
        libb.process_portfolio()

        deep_research_report = prompt_deep_research(libb)

        libb.analyze_sentiment(deep_research_report, report_type="Deep_Research")
        libb.save_deep_research(deep_research_report, slot="backtest")

        orders_json = parse_json(deep_research_report, "ORDERS_JSON")

        libb.save_orders(orders_json)
    return

def daily_flow(date):
    for model in MODELS:
        libb = LIBBmodel(f"user_side/runs/run_v1/{model}", run_date=date)
        libb.process_portfolio()

        daily_report = prompt_daily_report(libb)

        libb.analyze_sentiment(daily_report, report_type="Daily")
        libb.save_daily_update(daily_report, slot="backtest")

        orders_json = parse_json(daily_report, "ORDERS_JSON")

        libb.save_orders(orders_json)
    return

def main():
    start_date = pd.Timestamp.now().normalize()
    for i in range(1):
        run_date = start_date + pd.Timedelta(days=i)    
        day_num = run_date.weekday()

        if day_num  == 4: # Friday
            print("Friday: Running Weekly Flow...")
            weekly_flow(run_date)
        elif day_num < 4:
            print("Regular Weekday: Running Daily Flow...")
            daily_flow(run_date) # Mon-Thursday
        else:  # Weekend (optional, LIBB will automatically skip weekends)
            print("Weekend: Skipping...")
        print("Success!")


# -------------------------------------------------------------------
# BACKTEST
# Worldwide stocks ≤ 100 EUR, 1.000 EUR capital, 1 EUR/trade fee
# Free AI via Groq (set GROQ_API_KEY environment variable first)
# Backtesting period: rolling last HISTORY_WINDOW_DAYS days (default 14)
#                     override with start= and end= parameters
# -------------------------------------------------------------------

def _prompt_with_retry(
    libb,
    log_fn=print,
    cancel_event: threading.Event | None = None,
    max_retries: int = 2,
) -> dict:
    """
    Call prompt_smallcap and parse the JSON result.
    Retries up to max_retries times if parse_json fails (malformed output).
    Returns the parsed orders dict, or {"orders": []} as safe fallback.

    Cache-Skip: if a report file for this run_date already exists on disk,
    the LLM is not called at all — the cached text is re-parsed directly.
    """
    weekday = pd.Timestamp(libb.run_date).weekday()
    run_path = Path(libb._model_path)

    # ── Cache-Check ──────────────────────────────────────────────────────────
    if weekday == 4:
        cached_path = run_path / "research" / "deep_research" / f"deep_research - {libb.run_date} - backtest.txt"
    else:
        cached_path = run_path / "research" / "daily_reports" / f"daily_update - {libb.run_date} - backtest.txt"

    if cached_path.exists():
        log_fn(f"  [CACHED] Report für {libb.run_date} gefunden – LLM-Aufruf übersprungen.")
        cached_text = cached_path.read_text(encoding="utf-8")
        try:
            return parse_json(cached_text, "ORDERS_JSON")
        except Exception as e:
            log_fn(f"  [WARN] Cache-Parse fehlgeschlagen ({e}) – rufe LLM auf.")

    # ── Cancel-Check vor LLM-Aufruf ──────────────────────────────────────────
    if cancel_event and cancel_event.is_set():
        log_fn(f"  [ABGEBROCHEN] Vor LLM-Aufruf für {libb.run_date} gestoppt.")
        raise InterruptedError("Backtest abgebrochen")

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            if weekday == 4:
                report = prompt_deep_research(libb, log_fn=log_fn, cancel_event=cancel_event)
            else:
                report = prompt_daily_report(libb, log_fn=log_fn, cancel_event=cancel_event)
            orders_json = parse_json(report, "ORDERS_JSON")

            # Persist the report text
            if weekday == 4:
                libb.save_deep_research(report, slot="backtest")
            else:
                libb.save_daily_update(report, slot="backtest")

            libb.analyze_sentiment(report, report_type="Deep_Research" if weekday == 4 else "Daily")
            return orders_json

        except InterruptedError:
            raise  # Cancel direkt weitergeben
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                log_fn(f"  [retry {attempt + 1}/{max_retries}] parse/prompt error: {e}")
                # Cancel-sicheres Sleep
                for _ in range(3):
                    if cancel_event and cancel_event.is_set():
                        raise InterruptedError("Backtest abgebrochen")
                    time.sleep(1)
            else:
                log_fn(f"  [WARN] Alle Retries ausgeschöpft ({last_error}). Überspringe Orders für {libb.run_date}.")
                return {"orders": []}


def smallcap_backtest(
    run_dir: str,
    start: str | None = None,
    end: str | None = None,
    day_sleep: float = 1.5,
    model_sleep: float = 1.5,
    log_fn=print,
    cancel_event: threading.Event | None = None,
    reset_on_start: bool = False,
) -> None:
    """
    Run the backtesting workflow for an existing run.

    Historical data is fetched and injected into the selected run's portfolio.
    Days that already exist in portfolio_history are automatically skipped.

    Parameters
    ----------
    run_dir : str
        Directory of the existing run (e.g. "user_side/runs/run_v1/groq").
        starting_cash, commission and market_calendar are inherited from the
        run's config.json (written on first model start).
    start : str | None
        Start date (inclusive), ISO format. Defaults to HISTORY_WINDOW_DAYS days before today.
    end : str | None
        End date (inclusive), ISO format. Defaults to today.
    day_sleep : float   Seconds to sleep between days (yfinance rate limit).
    model_sleep : float Seconds to sleep before LLM call (API rate limit).
    reset_on_start : bool
        If True, delete all run artifacts before starting.
    """
    today = pd.Timestamp.now().normalize()
    if end is None:
        end = today.strftime("%Y-%m-%d")
    if start is None:
        start = (today - pd.Timedelta(days=HISTORY_WINDOW_DAYS)).strftime("%Y-%m-%d")

    date_range = pd.date_range(start=start, end=end, freq="D")

    # ── Inherit run config from disk (before potential reset) ────────────────
    # When reset_on_start=True we always use the hardcoded defaults so that a
    # stale config.json (e.g. written with old 100 EUR values) can never
    # "poison" the freshly-reset run.
    if reset_on_start:
        starting_cash   = STARTING_CASH_DEFAULT
        commission      = COMMISSION_DEFAULT
        market_calendar = MARKET_CALENDAR_DEFAULT
    else:
        config_path = Path(run_dir) / "config.json"
        run_config: dict = {}
        if config_path.exists():
            try:
                run_config = json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        starting_cash    = float(run_config.get("starting_cash",   STARTING_CASH_DEFAULT))
        commission       = float(run_config.get("commission",       COMMISSION_DEFAULT))
        market_calendar  = str  (run_config.get("market_calendar",  MARKET_CALENDAR_DEFAULT))

    # ── Optional: Run-Verzeichnis zurücksetzen ───────────────────────────────
    if reset_on_start:
        log_fn("⚠  Reset angefordert – lösche alle bisherigen Run-Daten …")
        try:
            _reset_libb = LIBBmodel(
                run_dir,
                starting_cash=starting_cash,
                commission=commission,
                market_calendar=market_calendar,
            )
            _reset_libb.reset_run(cli_check=False, auto_ensure=True)
            log_fn("✓  Run-Verzeichnis zurückgesetzt – starte mit leerem Portfolio.")
        except Exception as e:
            log_fn(f"  [WARN] Reset fehlgeschlagen: {e} – fahre trotzdem fort.")

    log_fn(f"{'='*55}")
    log_fn(f"  BACKTEST")
    log_fn(f"  Run-Dir  : {run_dir}")
    log_fn(f"  Zeitraum : {start} → {end}")
    log_fn(f"  Kapital  : {starting_cash:.2f} (aus config.json)")
    log_fn(f"  Gebühr   : {commission:.2f} / Kalender: {market_calendar}")
    log_fn(f"  Tage     : {sum(1 for d in date_range if d.weekday() < 5)} Handelstage")
    log_fn(f"{'='*55}")

    for run_date in date_range:
        # ── Cancel-Check am Anfang jedes Tages ──────────────────────────────
        if cancel_event and cancel_event.is_set():
            log_fn("[ABGEBROCHEN] Backtest wurde durch Benutzer gestoppt.")
            return

        weekday = run_date.weekday()
        if weekday >= 5:  # Wochenende
            continue

        day_type = "WEEKLY (deep research)" if weekday == 4 else "DAILY"
        log_fn(f"[{run_date.date()}] {day_type}")

        try:
            libb = LIBBmodel(
                run_dir,
                starting_cash=starting_cash,
                run_date=run_date,
                commission=commission,
                market_calendar=market_calendar,
            )

            # ── Skip-Guard: Datum bereits in portfolio_history ───────────────
            if (not libb.portfolio_history.empty and
                    str(run_date.date()) in libb.portfolio_history["date"].values):
                log_fn(f"  [SKIP] {run_date.date()} bereits verarbeitet – übersprungen.")
                continue

            libb.process_portfolio()

            # Cancel-Check vor dem Sleep
            if cancel_event and cancel_event.is_set():
                log_fn("[ABGEBROCHEN] Backtest wurde durch Benutzer gestoppt.")
                return

            # Groq Rate-Limit Buffer (Cancel-sicher)
            for _ in range(int(model_sleep * 2)):
                if cancel_event and cancel_event.is_set():
                    log_fn("[ABGEBROCHEN] Backtest wurde durch Benutzer gestoppt.")
                    return
                time.sleep(0.5)

            orders_json = _prompt_with_retry(libb, log_fn=log_fn, cancel_event=cancel_event)
            libb.save_orders(orders_json)

            n_orders = len(orders_json.get("orders", []))
            log_fn(f"  Orders gespeichert: {n_orders}")

        except InterruptedError:
            log_fn("[ABGEBROCHEN] Backtest gestoppt.")
            return
        except Exception as e:
            cause = e.__cause__ if e.__cause__ is not None else e
            log_fn(f"  [FEHLER] {run_date.date()}: {cause}")

        # Cancel-sicherer Sleep zwischen Tagen
        for _ in range(int(day_sleep * 2)):
            if cancel_event and cancel_event.is_set():
                log_fn("[ABGEBROCHEN] Backtest wurde durch Benutzer gestoppt.")
                return
            time.sleep(0.5)

    # ── Abschluss-Metriken ───────────────────────────────────────────────────
    log_fn("")
    log_fn("Generiere finale Metriken …")
    try:
        libb_final = LIBBmodel(
            run_dir,
            starting_cash=starting_cash,
            commission=commission,
            market_calendar=market_calendar,
        )

        ph       = libb_final.portfolio_history
        tl       = libb_final.trade_log
        pos_hist = libb_final.position_history

        # Performance-Metriken: benötigt mind. 2 unterschiedliche Equity-Werte
        if not ph.empty and ph["equity"].nunique() > 1:
            try:
                perf = libb_final.generate_performance_metrics(baseline_ticker="EWG")
                log_fn(f"  Sharpe (annual): {perf.get('sharpe_annual', 'n/a')}")
                log_fn(f"  Max Drawdown   : {perf.get('max_drawdown', 'n/a')}")
            except Exception as e:
                log_fn(f"  [WARN] Performance-Metriken fehlgeschlagen: {e}")
        else:
            log_fn("  Performance-Metriken übersprungen – noch keine Equity-Bewegung vorhanden.")

        # Behavioral-Metriken: benötigt mind. 1 Trade und 1 Position
        if not tl.empty and not pos_hist.empty:
            try:
                beh = libb_final.generate_behavior_metrics()
                log_fn(f"  Loss Aversion  : {beh.get('loss_aversion', 'n/a')}")
                log_fn(f"  Turnover Ratio : {beh.get('turnover_ratio', 'n/a')}")
            except Exception as e:
                log_fn(f"  [WARN] Behavioral-Metriken fehlgeschlagen: {e}")
        else:
            log_fn("  Behavioral-Metriken übersprungen – noch keine Handelstransaktionen vorhanden.")

    except Exception as e:
        log_fn(f"  [WARN] Metriken konnten nicht geladen werden: {e}")

    log_fn("")
    log_fn("✓ Backtest abgeschlossen.")


if __name__ == "__main__":
    # Beispiel: smallcap_backtest(run_dir="user_side/runs/run_v1/groq")
    pass
