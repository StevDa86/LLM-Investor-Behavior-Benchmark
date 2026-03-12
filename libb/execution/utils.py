import pandas as pd
from pathlib import Path
from ..other.types_file import Order
import datetime as dt
import pandas_market_calendars as mcal
import math

def load_df(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)

def append_log(path: Path, row: dict | pd.DataFrame) -> None:
    df = load_df(path)

    if df.columns.empty:
        raise RuntimeError("Schema missing: header not initialized")
    
    if isinstance(row, pd.DataFrame):
        row = row.reindex(columns=df.columns)
        row.to_csv(path, index=False, mode="a", header=False, encoding="utf-8",)

    elif isinstance (row, dict):
        row_df = pd.DataFrame([row]).reindex(columns=df.columns)
        row_df.to_csv(path, index=False, mode="a", header=False, encoding="utf-8",)
    else:
        raise RuntimeError(f"Invalid data type given for append_log(): {type(row)}. Row must be either a DataFrame or dict.")
    return

# TODO: Use enum codes for error reasoning instead of formatted strings

def order_to_trade_schema(order: Order,  *, executed_price: float | None, PnL: float | None, status: str, reason: str) -> dict:

        valid_order_actions_map = {"b": "BUY", "s": "SELL", "u": "UPDATE"}
        order_action = order.get("action").lower()
        validated_order_action = valid_order_actions_map.get(order_action, "MISSING")
        if executed_price is not None:
            cost_basis = round(executed_price * order.get("shares", math.nan), 2)
        else:
            cost_basis = math.nan

        if PnL is not None:
            PnL = round(PnL, 2)

        order_dict = {
            "date": order.get("date", "MISSING"),
            "ticker": order.get("ticker", "MISSING"),
            "action": validated_order_action,
            "order_type": order.get("order_type", "MISSING").upper(),
            "shares": order.get("shares", math.nan),
            "limit_price": order.get("limit_price", math.nan),
            "executed_price": executed_price,
            "stop_loss": order.get("stop_loss", math.nan),
            "cost_basis": cost_basis,
            "PnL": PnL,
            "rationale": order.get("rationale", "MISSING"),
            "confidence": order.get("confidence", "MISSING"),
            "status": status,
            "reason": reason,
                                }

                

        return order_dict

def catch_missing_order_data(order: Order, required_cols: list, trade_log_path: Path) -> bool:
    """Log failures for missing or null data required for order.
    Return True if needed data exists; False otherwise.
    """

    missing_cols = []
    for col in required_cols:
        if col not in order or order[col] is None:
            missing_cols.append(col)

    if missing_cols:
        reason = f"MISSING OR NULL ORDER INFO: {missing_cols}"
        trade_dict = order_to_trade_schema(order, executed_price=None, 
                                           PnL=None, status="FAILED", reason=reason)
        append_log(trade_log_path, trade_dict)
        return False

    return True

nyse = mcal.get_calendar("NYSE")

def is_nyse_open(date: dt.date) -> bool:
    """
    Check if the NYSE is open on a given date.

    Parameters
    ----------
    date : datetime.date
        The date to check.

    Returns
    -------
    bool
        True if NYSE is open, False otherwise.
    """
    schedule = nyse.schedule(start_date=date, end_date=date)
    return not schedule.empty

_calendar_cache: dict[str, mcal.MarketCalendar] = {}

def is_market_open(date: dt.date, calendar_name: str = "NYSE") -> bool:
    """
    Check if a given market calendar is open on a given date.

    Parameters
    ----------
    date : datetime.date
    calendar_name : str
        pandas_market_calendars exchange name (e.g. "NYSE", "XETRA", "LSE").
        Defaults to "NYSE".

    Returns
    -------
    bool
        True if the market is open, False otherwise.
    """
    if calendar_name not in _calendar_cache:
        _calendar_cache[calendar_name] = mcal.get_calendar(calendar_name)
    cal = _calendar_cache[calendar_name]
    schedule = cal.schedule(start_date=date, end_date=date)
    return not schedule.empty


def next_trading_day(from_date: dt.date, calendar_name: str = "NYSE", max_lookahead: int = 14) -> dt.date:
    """
    Return the next open trading day strictly after `from_date`.

    Parameters
    ----------
    from_date : datetime.date
        The reference date (today / run_date). The returned date is always > from_date.
    calendar_name : str
        pandas_market_calendars exchange name (e.g. "NYSE", "XETRA"). Defaults to "NYSE".
    max_lookahead : int
        Maximum days to search ahead before raising. Covers long holiday breaks.

    Returns
    -------
    datetime.date
        The next open trading day after `from_date`.
    """
    candidate = from_date + dt.timedelta(days=1)
    for _ in range(max_lookahead):
        if is_market_open(candidate, calendar_name):
            return candidate
        candidate += dt.timedelta(days=1)
    raise RuntimeError(
        f"No open trading day found within {max_lookahead} days after {from_date} "
        f"on calendar '{calendar_name}'."
    )
