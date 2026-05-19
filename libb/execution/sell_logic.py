from .portfolio_editing import reduce_position
from .utils import append_log, catch_missing_order_data, order_to_trade_schema, load_df
from libb.execution.get_market_data import download_data_on_given_date
from pathlib import Path
import pandas as pd
import pandas_market_calendars as mcal
from ..other.types_file import Order
from typing import cast

MIN_HOLD_TRADING_DAYS = 10
MAX_LOSS_EXCEPTION_PCT = -25.0   # allow early sell if unrealised loss exceeds this


def _trading_days_since_buy(ticker: str, order_date: str, trade_log_path: Path, market_calendar: str) -> int | None:
    """
    Return the number of market trading days between the last filled BUY for
    *ticker* and *order_date*.  Returns None when no filled BUY is found
    (position data inconsistency – caller should allow the sell to proceed).
    """
    df = load_df(trade_log_path)
    if df.empty:
        return None

    buys = df[
        (df["ticker"].str.upper() == ticker.upper()) &
        (df["action"] == "BUY") &
        (df["status"] == "FILLED")
    ]
    if buys.empty:
        return None

    last_buy_date = pd.to_datetime(buys["date"]).max().date()
    sell_date = pd.Timestamp(order_date).date()

    if sell_date <= last_buy_date:
        return 0

    try:
        cal = mcal.get_calendar(market_calendar)
        schedule = cal.schedule(start_date=last_buy_date, end_date=sell_date)
        # subtract 1: buy day itself is not counted as a held day
        return max(0, len(schedule) - 1)
    except Exception:
        return None


def _unrealised_loss_pct(portfolio_df: pd.DataFrame, ticker: str, current_price: float) -> float | None:
    """Return unrealised change in % relative to average cost. Negative = loss."""
    rows = portfolio_df[portfolio_df["ticker"] == ticker]
    if rows.empty:
        return None
    shares = rows.iloc[0]["shares"]
    cost_basis = rows.iloc[0]["cost_basis"]
    if not shares or not cost_basis:
        return None
    avg_cost = cost_basis / shares
    if avg_cost == 0:
        return None
    return ((current_price - avg_cost) / avg_cost) * 100.0


def process_sell(
    order: Order,
    portfolio_df: pd.DataFrame,
    cash: float,
    trade_log_path: Path,
    commission: float = 0.0,
    market_calendar: str = "NYSE",
) -> tuple[pd.DataFrame, float, bool]:
    ticker = order["ticker"].upper()
    order_type = order["order_type"].upper()
    date = order["date"]
    ticker_data = download_data_on_given_date(ticker, date)

    high = ticker_data["High"]
    open_price = ticker_data["Open"]

    shares = int(order["shares"])
    limit_price = float(cast(float, order["limit_price"]))

    row = portfolio_df.loc[portfolio_df["ticker"] == ticker].iloc[0]
    if shares > row["shares"]:
        reason = f"INSUFFICIENT SHARES: REQUESTED {shares}, AVAILABLE {row['shares']}"
        trade_dict = order_to_trade_schema(order, executed_price=None, PnL=None,
                                           status="FAILED", reason=reason)
        append_log(trade_log_path, trade_dict)
        return portfolio_df, cash, False

    # ------------------------------------------------------------------
    # MINIMUM HOLDING PERIOD — engine-enforced
    # STOPLOSS_MET orders bypass this check (they never reach process_sell).
    # Exception 1: unrealised loss > MAX_LOSS_EXCEPTION_PCT
    # Exception 2: no buy record found (data inconsistency – allow sell)
    # ------------------------------------------------------------------
    if order_type != "STOPLOSS_MET":
        ref_price = open_price if limit_price <= 0 else limit_price
        days_held = _trading_days_since_buy(ticker, date, trade_log_path, market_calendar)
        loss_pct  = _unrealised_loss_pct(portfolio_df, ticker, ref_price)

        exceeds_loss_limit = (loss_pct is not None and loss_pct <= MAX_LOSS_EXCEPTION_PCT)

        if days_held is not None and days_held < MIN_HOLD_TRADING_DAYS and not exceeds_loss_limit:
            reason = (
                f"MIN_HOLDING_PERIOD: only {days_held}/{MIN_HOLD_TRADING_DAYS} trading days held. "
                f"Exceptions: stop-loss trigger or unrealised loss >{abs(MAX_LOSS_EXCEPTION_PCT):.0f}%. "
                f"Current P&L: {loss_pct:.1f}%" if loss_pct is not None
                else f"MIN_HOLDING_PERIOD: only {days_held}/{MIN_HOLD_TRADING_DAYS} trading days held."
            )
            trade_dict = order_to_trade_schema(order, executed_price=None, PnL=None,
                                               status="REJECTED", reason=reason)
            append_log(trade_log_path, trade_dict)
            return portfolio_df, cash, False
    # ------------------------------------------------------------------

    if order_type == "LIMIT" and high < limit_price:
        reason = f"limit price of {limit_price} not met. (High: {high})"
        trade_dict = order_to_trade_schema(order, executed_price=None, PnL=None,
                                           status="FAILED", reason=reason)
        append_log(trade_log_path, trade_dict)
        return portfolio_df, cash, False

    elif order_type == "LIMIT":
        required_col = ["ticker", "limit_price", "shares"]
        if not catch_missing_order_data(order, required_col, trade_log_path):
            return portfolio_df, cash, False
        fill_price = open_price if open_price >= limit_price else limit_price
        proceeds = shares * fill_price - commission
        portfolio_df, buy_price = reduce_position(portfolio_df, ticker, shares)
        cash += proceeds
        pnl = proceeds - (buy_price * shares)
        trade_dict = order_to_trade_schema(order, executed_price=fill_price, PnL=pnl,
                                           status="FILLED", reason=f"commission={commission}")
        append_log(trade_log_path, trade_dict)
        return portfolio_df, cash, True

    elif order_type == "MARKET":
        required_col = ["ticker", "shares"]
        if not catch_missing_order_data(order, required_col, trade_log_path):
            return portfolio_df, cash, False
        proceeds = shares * open_price - commission
        portfolio_df, buy_price = reduce_position(portfolio_df, ticker, shares)
        cash += proceeds
        pnl = proceeds - (buy_price * shares)
        trade_dict = order_to_trade_schema(order, executed_price=open_price, PnL=pnl,
                                           status="FILLED", reason=f"commission={commission}")
        append_log(trade_log_path, trade_dict)
        return portfolio_df, cash, True

    else:
        reason = f"ORDER TYPE UNKNOWN: {order_type}"
        trade_dict = order_to_trade_schema(order, executed_price=None, PnL=None,
                                           status="FAILED", reason=reason)
        append_log(trade_log_path, trade_dict)
        return portfolio_df, cash, False
