from libb import LIBBmodel
from .prompt_orchestration.prompt_models import (
    prompt_deep_research,
    prompt_daily_report,
    prompt_fundamental_review,
)
from libb.other.parse import parse_json
import pandas as pd
from datetime import datetime

MODELS = ["groq", "openrouter", "gemini"]


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


# ─── Flows ────────────────────────────────────────────────────────────────────

def deep_research_flow(date, slot: str, log_fn=print):
    """Nightly strategy review (Mo–Fr ~22:00). Produces orders for next trading day."""
    for model in MODELS:
        try:
            libb = LIBBmodel(f"user_side/runs/run_v1/{model}", run_date=date)
            libb.process_portfolio(slot=slot)
            deep_research_report = prompt_deep_research(libb, log_fn=log_fn)
            libb.save_deep_research(deep_research_report, slot=slot)
            orders_json = parse_json(deep_research_report, "ORDERS_JSON")
            libb.save_orders(orders_json)
            libb.analyze_sentiment(deep_research_report, report_type="Deep_Research")
            log_fn(f"[deep_research_flow] ✓ Modell '{model}' ({date}) abgeschlossen.")
        except Exception as e:
            log_fn(f"[deep_research_flow] [FEHLER] Modell '{model}' ({date}): {e}")
    return


def fundamental_flow(date, slot: str, log_fn=print):
    """Saturday fundamental review. Pure company analysis – no orders placed."""
    for model in MODELS:
        try:
            libb = LIBBmodel(f"user_side/runs/run_v1/{model}", run_date=date)
            libb.process_portfolio(slot=slot)
            fundamental_report = prompt_fundamental_review(libb, log_fn=log_fn)
            libb.save_deep_research(fundamental_report, slot=slot)   # reuses deep_research storage
            libb.analyze_sentiment(fundamental_report, report_type="Fundamental_Review")
            log_fn(f"[fundamental_flow] ✓ Modell '{model}' ({date}) abgeschlossen.")
        except Exception as e:
            log_fn(f"[fundamental_flow] [FEHLER] Modell '{model}' ({date}): {e}")
    return


def daily_flow(date, slot: str, log_fn=print):
    """Active trading during market hours (Mo–Fr 09:00 / 16:00 / 18:00)."""
    for model in MODELS:
        try:
            libb = LIBBmodel(f"user_side/runs/run_v1/{model}", run_date=date)
            libb.process_portfolio(slot=slot)
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

def main(slot: str | None = None, log_fn=print):
    if slot is None:
        slot = _current_slot()

    today = pd.Timestamp.now().date()
    day_num = today.weekday()  # 0=Mon … 4=Fri, 5=Sat, 6=Sun

    if slot == "night":
        # Nightly deep research after US market close – Mo–Fr only
        if day_num < 5:
            log_fn(f"[Workflow] Nightly Deep Research [{today}] ...")
            deep_research_flow(today, slot, log_fn=log_fn)
        else:
            log_fn("[Workflow] Nightly slot on weekend – skipping.")

    elif slot == "weekend":
        # Saturday fundamental review – only runs on Saturday
        if day_num == 5:
            log_fn(f"[Workflow] Saturday Fundamental Review [{today}] ...")
            fundamental_flow(today, slot, log_fn=log_fn)
        else:
            log_fn("[Workflow] Weekend slot on non-Saturday – skipping.")

    else:
        # Daily trading slots: morning / noon / midday / evening – Mo–Fr only
        if day_num < 5:
            log_fn(f"[Workflow] Daily Trading [{slot}] [{today}] ...")
            daily_flow(today, slot, log_fn=log_fn)
        else:
            log_fn("[Workflow] Weekend – skipping.")

    log_fn("[Workflow] ✓ abgeschlossen.")


if __name__ == "__main__":
    main()
