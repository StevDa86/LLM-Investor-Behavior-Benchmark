from libb import LIBBmodel
from .prompt_orchestration.prompt_models import prompt_deep_research, prompt_daily_report
from libb.other.parse import parse_json
import pandas as pd

MODELS = ["groq"]

def _already_processed(libb: LIBBmodel) -> bool:
    """Return True if run_date is already recorded in portfolio_history."""
    if libb.portfolio_history.empty:
        return False
    return str(libb.run_date) in libb.portfolio_history["date"].values

def weekly_flow(date):
    for model in MODELS:
        libb = LIBBmodel(f"user_side/runs/run_v1/{model}", run_date=date)
        if _already_processed(libb):
            print(f"[SKIP] {date} already processed for {model} – skipping.")
            continue
        libb.process_portfolio()
        deep_research_report = prompt_deep_research(libb)
        libb.save_deep_research(deep_research_report)
        orders_json = parse_json(deep_research_report, "ORDERS_JSON")
        libb.save_orders(orders_json)
        libb.analyze_sentiment(deep_research_report, report_type="Deep_Research")
    return

def daily_flow(date):
    for model in MODELS:
        libb = LIBBmodel(f"user_side/runs/run_v1/{model}", run_date=date)
        if _already_processed(libb):
            print(f"[SKIP] {date} already processed for {model} – skipping.")
            continue
        libb.process_portfolio()
        daily_report = prompt_daily_report(libb)
        libb.analyze_sentiment(daily_report, report_type="Daily")
        libb.save_daily_update(daily_report)
        orders_json = parse_json(daily_report, "ORDERS_JSON")
        libb.save_orders(orders_json)
    return

def main():
    today = pd.Timestamp.now().date()
    day_num = today.weekday()

    if day_num == 4:  # Friday
        print("Friday: Running Weekly Flow...")
        weekly_flow(today)
    elif day_num < 4:  # Mon–Thu
        print("Regular Weekday: Running Daily Flow...")
        daily_flow(today) # Mon-Thursday
    else:  # Weekend
        print("Weekend: Skipping...")
        pass
    print("Success!")


if __name__ == "__main__":
    main()