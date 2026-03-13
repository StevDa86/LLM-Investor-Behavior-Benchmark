from libb.model import LIBBmodel
from user_side.prompt_orchestration.get_prompt_data import get_market_candidates


# -------------------------------------------------------------------
# STATIC PROMPT SECTIONS
# -------------------------------------------------------------------

SYSTEM_HEADER = """## System
You are a senior equity research analyst conducting a WEEKEND FUNDAMENTAL REVIEW.
Markets are closed. There is no time pressure and no orders will be placed today.
Your sole task is to provide rigorous, independent fundamental analysis of every
held position and every eligible watchlist candidate.
This analysis will directly guide all trading decisions for the coming week.
Today is {today}.
"""

PURPOSE = """
## PURPOSE
This is a pure research session — NOT a trading session.
• Do NOT produce any orders or ORDERS_JSON.
• Base all analysis on your own fundamental knowledge of each company:
  financials, business model, competitive landscape, sector dynamics.
• Be brutally honest: if a holding is fundamentally weak, say so.
• Your analysis must be actionable: each conclusion should tell the daily
  trading system what to do with a position in the coming week.
"""

TRADER_MINDSET = """
## TRADER MINDSET — WEEKLY PROFIT FOCUS (MANDATORY)
This portfolio is managed by an ACTIVE STOCK TRADER targeting weekly profit.
Every conclusion in this analysis must be judged through that lens.

KEY EXPECTATIONS FOR THIS REVIEW:
• For EVERY held position: explicitly answer "Can this position profit THIS WEEK?"
  – YES with catalyst → recommend HOLD or ADD.
  – NO clear near-term catalyst → recommend EXIT and capital redeployment.
• SELL is always executable — sell fees come from proceeds, not from cash.
  Never recommend holding a weak position to "avoid paying the fee".
• For candidates: rank by likelihood of generating profit within 5 trading days.
• Capital efficiency beats emotional attachment. A small booked loss now is
  better than a larger unrealised loss next week.
• Longer holds ARE valid — but only with strong fundamental justification AND
  positive price momentum. Dead money must be freed.
"""

FUNDAMENTAL_REQUIREMENTS = """
## FUNDAMENTAL ANALYSIS REQUIREMENTS
For EVERY held position AND every watchlist candidate, cover all 6 areas:

1. BUSINESS MODEL
   • Core revenue streams and target market
   • Sustainability and scalability of the model
   • Dependence on macro conditions or single customers

2. FINANCIAL HEALTH
   • Revenue trend: growing / stable / declining
   • Profitability: profitable / path to profit / loss-making
   • Debt level: manageable / concerning / dangerous
   • Cash runway (for loss-making companies): months remaining

3. COMPETITIVE POSITION (MOAT)
   • What protects this company from competitors?
   • Type of moat: network effect / switching cost / brand / patents / cost leadership
   • Is the moat widening, stable, or eroding?

4. GROWTH CATALYSTS
   • Near-term catalysts (< 3 months): product launches, earnings, partnerships
   • Medium-term catalysts (3–12 months): market expansion, restructuring, sector tailwinds
   • Long-term thesis: why should this company be worth more in 2–3 years?

5. KEY RISKS
   • Top 3 risks: regulatory / competition / execution / macro / balance sheet
   • Severity (Low / Medium / High / Critical) and probability (Unlikely / Possible / Likely)

6. CONVICTION VERDICT
   • STRONG BUY | BUY | HOLD | REDUCE | EXIT
   • One-sentence summary of your conviction and the single most important reason
"""

STRATEGY_SECTION = """
## WEEKLY STRATEGY PLAN
After completing the fundamental analysis, provide a structured strategy plan:

### PORTFOLIO HEALTH SUMMARY
• Overall portfolio conviction (0.0–1.0) with justification
• Weakest holding: which position is most at risk and why?
• Strongest holding: which position has the best fundamental outlook?
• Cash allocation comment: is the current cash level appropriate?

### WATCHLIST PRIORITY RANKING
Rank the eligible candidates (≤ 10 EUR) from most to least attractive.
For each: company name, ticker, 2-sentence buy thesis, key risk.
Maximum 5 ranked candidates.

### WEEKLY PROFIT ASSESSMENT (MANDATORY)
For EACH held position answer explicitly:
• Likely to profit THIS WEEK? YES / NO / UNCERTAIN
• If NO or UNCERTAIN: recommend EXIT (with suggested limit price) OR justify HOLD with
  a specific catalyst expected within 5 trading days.
• Reminder: selling costs nothing from cash — fee is deducted from proceeds.
  Never hold a weak position just to avoid the sell fee.

### POSITIONS TO WATCH CLOSELY NEXT WEEK
• Any position that should be sold on the next price weakness (with trigger price)?
• Any position that deserves adding on the next price dip (with target entry zone)?
• Any stop-loss levels that should be reviewed or tightened?

### COMING WEEK OUTLOOK
• Overall market environment (inferred from fundamentals + macro knowledge)
• Key company-specific events to monitor for held positions
• Any sector rotation signals visible in the candidate universe?
"""

CONTEXT_BLOCK = """
## CONTEXT
### Current Portfolio State
{portfolio}

### Recent Execution Log (last 4 weeks, including failed orders)
{execution_log}

### Account Overview
• Available cash : {cash:.2f} EUR
• Trading fee    : {commission:.2f} EUR per filled order (round-trip cost: {round_trip:.2f} EUR)
"""

CANDIDATE_SECTION = """
## ELIGIBLE MARKET CANDIDATES (≤ 10 EUR / USD as of today)
The following stocks from the candidate universe currently trade below the price limit.
Analyse fundamentals for EVERY ticker listed — this is your research universe for the
coming week. You are not limited to this list for analysis depth, but only these tickers
are eligible for new buys next week.

{candidates}
"""

OUTPUT_FORMAT = """
## OUTPUT FORMAT (STRICT)
Produce exactly three tagged blocks — no other text outside these blocks:

<FUNDAMENTAL_ANALYSIS>
### HELD POSITIONS
[Full 6-area analysis for each held position]

### WATCHLIST CANDIDATES
[Full 6-area analysis for each candidate ≤ 10 EUR]
</FUNDAMENTAL_ANALYSIS>

<WATCHLIST_RECOMMENDATION>
[Complete weekly strategy plan as specified in WEEKLY STRATEGY PLAN above]
</WATCHLIST_RECOMMENDATION>

<CONFIDENCE_LVL>
0.75
</CONFIDENCE_LVL>
"""


# -------------------------------------------------------------------
# MAIN FUNCTION
# -------------------------------------------------------------------

def create_fundamental_review_prompt(libb: LIBBmodel) -> str:
    today = libb.run_date
    portfolio = libb.portfolio
    commission = libb.commission
    cash = libb.cash

    # Portfolio block
    if portfolio.empty:
        portfolio_text = (
            f"  No active positions.\n"
            f"  Available cash: {cash:.2f} EUR\n"
            f"  This is a FRESH portfolio — focus your analysis on the best candidates\n"
            f"  to initiate next week. Rank your top 5 picks with full justification."
        )
    else:
        unavailable = getattr(libb, "unavailable_tickers", [])
        portfolio_text = "  " + portfolio.to_string(index=False).replace("\n", "\n  ")
        if unavailable:
            portfolio_text += (
                f"\n\n  ⚠ NO MARKET DATA – POSSIBLY DELISTED: {', '.join(unavailable)}\n"
                "  → Prices shown for these tickers are STALE (last known value).\n"
                "  → Include EXIT recommendation for each delisted position.\n"
            )

    # Execution log
    execution_log = libb.recent_execution_logs()
    execution_log_text = (
        execution_log.to_string(index=False)
        if not isinstance(execution_log, str) and not execution_log.empty
        else "No recent trade logs."
    )

    # Candidates (exclude already-held tickers)
    already_held = list(portfolio["ticker"].str.upper()) if not portfolio.empty else []
    candidates_text = get_market_candidates(today, price_limit=10.0, already_held=already_held)

    return (
        SYSTEM_HEADER.format(today=today)
        + PURPOSE
        + TRADER_MINDSET
        + FUNDAMENTAL_REQUIREMENTS
        + STRATEGY_SECTION
        + CANDIDATE_SECTION.format(candidates=candidates_text)
        + CONTEXT_BLOCK.format(
            portfolio=portfolio_text,
            execution_log=execution_log_text,
            cash=cash,
            commission=commission,
            round_trip=commission * 2,
        )
        + OUTPUT_FORMAT
    )

