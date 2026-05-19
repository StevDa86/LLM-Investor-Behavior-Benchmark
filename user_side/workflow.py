from libb import LIBBmodel
from .prompt_orchestration.prompt_models import (
    prompt_deep_research,
    prompt_daily_report,
    prompt_fundamental_review,
)
from libb.other.parse import parse_json
from typing import Callable
import pandas as pd
from datetime import datetime

MODELS = ["groq", "openrouter", "gemini"]

STARTING_CASH = 1_000.0
COMMISSION    = 1.0
BUDGET_FLOOR  = 0.30   # stop trading if portfolio value drops below 30% of start


def _current_slot() -> str:
    """Determine the time slot based on the current local time.

    before 12:00  → 'morning'
    12:00–12:59   → 'noon'
    13:00–15:59   → 'midday'
    16:00–21:59   → 'evening'
    22:00+        → 'night'
    """
    hour = datetime.now().hour
    if hour < 12:
        return "morning"
    elif hour < 13:
        return "noon"
    elif hour < 16:
        return "midday"
    elif hour < 22:
        return "evening"
    else:
        return "night"


def _budget_ok(libb: LIBBmodel, log_fn: Callable[..., None]) -> bool:
    """Return False and log a warning when portfolio value is below the budget floor."""
    positions_value = libb.portfolio["market_value"].fillna(0).sum() if not libb.portfolio.empty else 0.0
    total = libb.cash + positions_value
    floor = libb.STARTING_CASH * BUDGET_FLOOR
    if total < floor:
        log_fn(
            f"  ⚠ Budget-Schutz: Portfoliowert {total:.2f} EUR < "
            f"{floor:.2f} EUR (={BUDGET_FLOOR*100:.0f}% von {libb.STARTING_CASH:.0f} EUR). "
            "Flow übersprungen – kein weiteres Trading bis zur manuellen Überprüfung."
        )
        return False
    return True


# ─── Flows ────────────────────────────────────────────────────────────────────

def deep_research_flow(date, slot: str, log_fn: Callable[..., None] = print):
    """Nightly strategy review (Mo–Fr ~22:00). Produces orders for next trading day."""
    for model in MODELS:
        try:
            libb = LIBBmodel(
                f"user_side/runs/run_v1/{model}",
                run_date=date,
                starting_cash=STARTING_CASH,
                commission=COMMISSION,
            )
            libb.process_portfolio(slot=slot)
            if not _budget_ok(libb, log_fn):
                continue
            deep_research_report = prompt_deep_research(libb, log_fn=log_fn)
            libb.save_deep_research(deep_research_report, slot=slot)
            orders_json = parse_json(deep_research_report, "ORDERS_JSON")
            libb.merge_orders(orders_json)
            libb.analyze_sentiment(deep_research_report, report_type="Deep_Research")
            log_fn(f"[deep_research_flow] ✓ Modell '{model}' ({date}) abgeschlossen.")
        except Exception as e:
            log_fn(f"[deep_research_flow] [FEHLER] Modell '{model}' ({date}): {e}")
    return


def fundamental_flow(date, slot: str, log_fn: Callable[..., None] = print):
    """Saturday fundamental review. Pure company analysis – no orders placed."""
    for model in MODELS:
        try:
            libb = LIBBmodel(
                f"user_side/runs/run_v1/{model}",
                run_date=date,
                starting_cash=STARTING_CASH,
                commission=COMMISSION,
            )
            libb.process_portfolio(slot=slot)
            if not _budget_ok(libb, log_fn):
                continue
            fundamental_report = prompt_fundamental_review(libb, log_fn=log_fn)
            libb.save_deep_research(fundamental_report, slot=slot)
            libb.analyze_sentiment(fundamental_report, report_type="Fundamental_Review")
            log_fn(f"[fundamental_flow] ✓ Modell '{model}' ({date}) abgeschlossen.")
        except Exception as e:
            log_fn(f"[fundamental_flow] [FEHLER] Modell '{model}' ({date}): {e}")
    return


def daily_flow(date, slot: str, log_fn: Callable[..., None] = print):
    """Active trading during market hours (Mo–Fr 09:00 / 16:00 / 18:00)."""
    for model in MODELS:
        try:
            libb = LIBBmodel(
                f"user_side/runs/run_v1/{model}",
                run_date=date,
                starting_cash=STARTING_CASH,
                commission=COMMISSION,
            )
            libb.process_portfolio(slot=slot)
            if not _budget_ok(libb, log_fn):
                continue
            daily_report = prompt_daily_report(libb, log_fn=log_fn)
            libb.analyze_sentiment(daily_report, report_type="Daily")
            libb.save_daily_update(daily_report, slot=slot)
            orders_json = parse_json(daily_report, "ORDERS_JSON")
            libb.save_orders(orders_json)
            log_fn(f"[daily_flow] ✓ Modell '{model}' ({date}) abgeschlossen.")
        except Exception as e:
            log_fn(f"[daily_flow] [FEHLER] Modell '{model}' ({date}): {e}")
    return


# ─── Einstieg ─────────────────────────────────────────────────────────────────

def main(slot: str | None = None, log_fn: Callable[..., None] = print):
    if slot is None:
        slot = _current_slot()

    today = pd.Timestamp.now().date()
    day_num = today.weekday()  # 0=Mon … 4=Fri, 5=Sat, 6=Sun

    if slot == "night":
        if day_num < 5:
            log_fn(f"[Workflow] Nightly Deep Research [{today}] ...")
            deep_research_flow(today, slot, log_fn=log_fn)
        else:
            log_fn("[Workflow] Nightly slot on weekend – skipping.")

    elif slot == "weekend":
        if day_num == 5:
            log_fn(f"[Workflow] Saturday Fundamental Review [{today}] ...")
            fundamental_flow(today, slot, log_fn=log_fn)
        else:
            log_fn("[Workflow] Weekend slot on non-Saturday – skipping.")

    else:
        if day_num < 5:
            log_fn(f"[Workflow] Daily Trading [{slot}] [{today}] ...")
            daily_flow(today, slot, log_fn=log_fn)
        else:
            log_fn("[Workflow] Weekend – skipping.")

    log_fn("[Workflow] ✓ abgeschlossen.")


if __name__ == "__main__":
    main()
