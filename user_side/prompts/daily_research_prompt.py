from libb.model import LIBBmodel
from libb.execution.utils import next_trading_day
from user_side.prompt_orchestration.get_prompt_data import get_market_candidates

MAX_POSITIONS = 5

# -------------------------------------------------------------------
# STATIC SECTIONS (portfolio-state-independent)
# -------------------------------------------------------------------

CAPITAL_RULE = """
## CAPITAL RULE
Use the live portfolio state provided (cash, positions, cost basis, stops, pnl).
Do NOT reset or assume any starting capital.
"""

PORTFOLIO_SECTION = """
## CURRENT PORTFOLIO
{portfolio_text}
"""

LOGS_SECTION = """
## RECENT EXECUTION LOGS
{logs_text}
"""

FAILED_ORDER_HANDLING = """
## FAILED ORDER HANDLING
Execution log may show: "limit not met", "insufficient cash",
"MAX_POSITIONS_REACHED (5)". Do NOT overreact or revenge trade.
Adjust only if clearly justified.
"""

PRE_BUY_FUNDAMENTAL_RULE = """
## PRE-BUY FUNDAMENTAL ANALYSIS (MANDATORY FOR NEW TICKERS)
Before placing a BUY order for any ticker NOT currently in the portfolio,
you MUST include a short fundamental analysis in the DAILY_ANALYSIS block:
  • Business model: what does the company do?
  • Financial health: profitable / path to profit / loss-making? Debt level?
  • Competitive moat: what protects it from competitors?
  • Key catalyst: why buy NOW specifically?
  • Key risk: what is the single biggest downside risk?
Skipping this analysis for a new ticker is NOT allowed.
Only after completing this check may you place the BUY order.
"""

SELL_FEE_RULE = """
## SELL — ALWAYS POSSIBLE (no upfront cash needed)
A SELL order executes as long as you hold the shares — regardless of cash balance.
The {commission:.2f} EUR fee is deducted from the SALE PROCEEDS, NOT from your cash.
  • Sell proceeds added to cash = (shares × fill_price) − {commission:.2f} EUR
  • You NEVER need a cash reserve to sell a position.
  • Low or zero cash is NOT a reason to hold a losing or stagnant position.
→ Use SELL freely to free up capital. The fee pays itself from what you receive.
"""

BUY_CASH_RULE = """
## CASH RULE FOR BUYS (HARD)
Every BUY costs cash upfront: (shares × fill_price) + {commission:.2f} EUR fee.
Never place a buy order if total cost exceeds available cash.
Available cash for new buys = cash shown in the portfolio above.
"""

TRADER_MINDSET = """
## TRADER MINDSET — WEEKLY PROFIT FOCUS (MANDATORY)
You are an ACTIVE STOCK TRADER. Your job is to grow this portfolio with real,
measurable profit. Think like a professional trader who reviews results weekly.

CORE PRINCIPLES:
• PROFIT OR STAY OUT: Only buy when you have a clear, realistic profit thesis
  after fees. "It might go up" is not a thesis. No conviction = no trade.
• WEEKLY ACCOUNTABILITY: Every week ask: is each position making money or blocking
  capital? A position that hasn't moved in a week deserves an exit review.
• SELL TO REDEPLOY: Selling a flat or losing position to move capital into a better
  opportunity IS good trading — not a failure. This is capital efficiency.
• HOLD ONLY WITH REASON: Holding is justified only when price action is positive
  OR a specific near-term catalyst is expected within days. Otherwise exit.
• LOW CASH = SELL SIGNAL: If cash is low and a better opportunity exists, sell
  the weakest position first. Sells cost nothing from cash — fee comes from proceeds.
• LONGER HOLDS ARE OK — but only for positions showing clear upward momentum or
  a confirmed near-term catalyst. Do not hold just to avoid booking a loss.
"""

CONCENTRATION_RULE = """
## CONCENTRATION RULE
Concentration > 60% in any single position: justify clearly OR reduce exposure.
"""

TRADING_FEE_RULE = """
## TRADING FEE & PROFIT REQUIREMENT
Every filled order costs {commission:.2f} EUR flat, deducted automatically.
Factor this into position sizing. Minimum recommended trade: {min_trade:.2f} EUR
(fee ≤ 5% of trade value).

**PROFIT GOAL — this is mandatory, not optional:**
• The objective is to generate REAL PROFIT — not just activity.
• A complete round-trip (1 buy + 1 sell) costs 2 × {commission:.2f} = {round_trip:.2f} EUR in fees alone.
• A trade is only worthwhile if:
    (expected exit price − entry price) × shares  >  {round_trip:.2f} EUR  (round-trip fee)
• Before placing a BUY, estimate a realistic exit target and verify:
    expected profit after fees  >  0
• Limit prices must be realistic — setting a limit far below the current price
  almost guarantees the order will never fill (see: "limit price not met" failures).
  A realistic limit is within 1–3% below the last closing price.
"""

UNIVERSE_RULE = """
## UNIVERSE RULE
• Only stocks priced ≤ 10 EUR (or local currency equivalent).
• MAX 5 positions simultaneously. Engine-enforced.
• NO new ticker while holding 5 — a slot opens only when a SELL is FILLED.
• Ticker format (yfinance): US: plain | XETRA: TICKER.DE | London: TICKER.L
  Amsterdam: TICKER.AS | Paris: TICKER.PA | Toronto: TICKER.TO
• CRITICAL: Only use tickers that are actively traded with significant volume.
  Do NOT invent or guess ticker symbols.
"""

MARKET_CANDIDATES_SECTION = """
## VERIFIED MARKET CANDIDATES (≤ 10 EUR / USD as of today)
The following stocks from the candidate universe currently trade BELOW the
price limit. You MUST pick from this list when opening new positions.
Do NOT use any ticker NOT in this list unless it is already in your portfolio.

{candidates}

→ Choose tickers from the list above. Set your limit_price ≤ the Close shown.
"""

OUTPUT_FORMAT = """
## OUTPUT FORMAT
Output exactly three blocks:

<DAILY_ANALYSIS>
...analysis, rationale for each decision...
</DAILY_ANALYSIS>

<ORDERS_JSON>
{"orders": [
  {"action":"b","ticker":"TICK.XX","shares":N,"order_type":"LIMIT",
   "limit_price":0.00,"time_in_force":"DAY","date":"YYYY-MM-DD",
   "stop_loss":0.00,"rationale":"...","confidence":0.0}
]}
</ORDERS_JSON>

If no trade: <ORDERS_JSON>{"orders": []}</ORDERS_JSON>

<CONFIDENCE_LVL>
0.65
</CONFIDENCE_LVL>

JSON MUST be pure — no extra text, comments, or markdown.
"""


# -------------------------------------------------------------------
# DYNAMIC SECTIONS (depend on portfolio state)
# -------------------------------------------------------------------

def _system_header(today, positions_count: int, free_slots: int, cash: float) -> str:
    if positions_count == 0:
        situation = (
            f"Your portfolio is EMPTY. You have {cash:.2f} EUR and {free_slots} open slots.\n"
            "You MUST initiate at least 1 new buy position today. "
            "Holding all-cash is NOT acceptable — deploy capital."
        )
    elif free_slots > 0:
        if cash < 5.0:
            situation = (
                f"You hold {positions_count} position(s) with {free_slots} open slot(s) "
                f"but only {cash:.2f} EUR cash — not enough for a new buy.\n"
                "ACTION REQUIRED: SELL your weakest or most stagnant position first to "
                "generate cash, then redeploy into a better candidate.\n"
                "Remember: sell fees come from proceeds — you need ZERO cash to sell."
            )
        else:
            situation = (
                f"You hold {positions_count} position(s) with {free_slots} open slot(s) "
                f"and {cash:.2f} EUR available cash.\n"
                "Manage existing positions AND actively seek new candidates to fill open slots. "
                "Opening new positions is strongly encouraged when suitable stocks exist."
            )
    else:
        situation = (
            f"Your portfolio is FULL ({MAX_POSITIONS}/{MAX_POSITIONS} positions). "
            f"Available cash: {cash:.2f} EUR.\n"
            "Evaluate every holding: HOLD, ADD shares to existing position, TRIM, or EXIT."
        )

    return (
        f"## System\n"
        f"You are an ACTIVE STOCK TRADER in DAILY Mode. Today is {today}.\n"
        f"Your mission: grow this portfolio with real, measurable weekly profit.\n\n"
        f"{situation}\n\n"
        "NO NEWS MODE: base all decisions strictly on price action, stop-loss levels,\n"
        "fundamentals (from your own knowledge), and portfolio logic.\n"
        "Do NOT fabricate or invent news, events, or catalysts.\n"
    )


def _objectives(positions_count: int, free_slots: int, execution_date: str) -> str:
    max_orders = min(free_slots + 2, 3) if free_slots > 0 else 2

    if positions_count == 0:
        return (
            "\n## DAILY OBJECTIVES\n"
            "• You MUST place at least 1 buy order for a stock priced ≤ 10 EUR.\n"
            "• Choose from any major exchange (XETRA, NYSE, NASDAQ, LSE, Euronext, etc.).\n"
            "• Set a stop-loss on every buy (typically 10–20% below entry price).\n"
            "• Full integer shares only. LIMIT orders preferred.\n"
            f"• Execution_date for ALL orders: {execution_date}  ← use this exact date, no other.\n"
            "• Allocate at least 20 EUR per position (keep fee impact below 5%).\n"
        )
    elif free_slots > 0:
        return (
            f"\n## DAILY OBJECTIVES\n"
            f"• Existing positions: check stop-loss triggers, price action, unrealized PnL.\n"
            f"  → For each: decide HOLD, ADD, TRIM, or EXIT.\n"
            f"  → If a position is flat or losing with no clear catalyst → EXIT to free capital.\n"
            f"• Open slots ({free_slots} available): actively evaluate new candidates ≤ 10 EUR.\n"
            f"  → Initiate a new position if a suitable stock exists. Do not stay in cash unnecessarily.\n"
            f"  → If cash is too low for a new buy: SELL the weakest position first, then buy.\n"
            f"    (Sell fee is deducted from proceeds — no cash needed to execute a sell.)\n"
            f"• Up to {max_orders} orders today (buys + sells combined). LIMIT DAY only.\n"
            f"• Full integer shares. Stop-loss required on all new buys.\n"
            f"• Execution_date for ALL orders: {execution_date}  ← use this exact date, no other.\n"
        )
    else:
        return (
            "\n## DAILY OBJECTIVES\n"
            "• Portfolio is full — no new tickers until an existing position is sold.\n"
            "• Check every position for stop-loss triggers and price action.\n"
            "• Decide for each: HOLD, ADD shares (uses cash), TRIM, or EXIT.\n"
            "• Up to 2 orders today. LIMIT DAY only. Full integer shares.\n"
            f"• Execution_date for ALL orders: {execution_date}  ← use this exact date, no other.\n"
        )


# -------------------------------------------------------------------
# MAIN FUNCTION
# -------------------------------------------------------------------

def create_daily_prompt(libb: LIBBmodel) -> str:
    portfolio  = libb.portfolio
    today      = libb.run_date
    commission = libb.commission
    logs       = libb.recent_execution_logs()

    positions_count = len(portfolio) if not portfolio.empty else 0
    free_slots      = MAX_POSITIONS - positions_count
    cash            = libb.cash

    # Compute the next open trading day for this run's market calendar
    execution_date = str(next_trading_day(today, libb.market_calendar))

    # Portfolio block
    if portfolio.empty:
        portfolio_text = (
            f"No active positions.\n"
            f"Available cash : {cash:.2f} EUR\n"
            f"Open slots     : {free_slots} / {MAX_POSITIONS}\n"
            f"Trading fee    : {commission:.2f} EUR per filled order"
        )
    else:
        portfolio_text = (
            f"Positions ({positions_count}/{MAX_POSITIONS}), "
            f"free slots: {free_slots}, "
            f"available cash: {cash:.2f} EUR\n\n"
            + portfolio.to_string(index=False)
        )

    # Warn about tickers with no current market data (possibly delisted)
    unavailable = getattr(libb, "unavailable_tickers", [])
    if unavailable:
        portfolio_text += (
            f"\n\n⚠ NO MARKET DATA – POSSIBLY DELISTED: {', '.join(unavailable)}\n"
            "→ Prices shown for these tickers are STALE (last known value).\n"
            "→ You MUST place a SELL order for each of these positions to free capital.\n"
            "→ Use a MARKET or low LIMIT order to ensure execution.\n"
        )

    # Logs block
    logs_text = (
        logs.to_string(index=False)
        if not isinstance(logs, str) and not logs.empty
        else "No recent trade logs."
    )

    min_trade_value = commission / 0.05 if commission > 0 else 0.0

    # Candidates block – fetch live/historical prices for the universe
    already_held = list(portfolio["ticker"].str.upper()) if not portfolio.empty else []
    candidates_text = get_market_candidates(today, price_limit=10.0, already_held=already_held)

    return (
        _system_header(today, positions_count, free_slots, cash)
        + CAPITAL_RULE
        + PORTFOLIO_SECTION.format(portfolio_text=portfolio_text)
        + LOGS_SECTION.format(logs_text=logs_text)
        + _objectives(positions_count, free_slots, execution_date)
        + FAILED_ORDER_HANDLING
        + PRE_BUY_FUNDAMENTAL_RULE
        + TRADER_MINDSET
        + SELL_FEE_RULE.format(commission=commission)
        + BUY_CASH_RULE.format(commission=commission)
        + CONCENTRATION_RULE
        + TRADING_FEE_RULE.format(commission=commission, min_trade=min_trade_value, round_trip=commission * 2)
        + UNIVERSE_RULE
        + MARKET_CANDIDATES_SECTION.format(candidates=candidates_text)
        + OUTPUT_FORMAT
    )
