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
This analysis will directly guide all trading decisions for the coming weeks.
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
  trading system what to do with a position over the coming weeks.
"""

INVESTOR_MINDSET = """
## INVESTOR MINDSET — THESIS-DRIVEN HOLDING (MANDATORY)
This portfolio is managed by a PATIENT STOCK INVESTOR targeting long-term capital growth.
Every conclusion in this analysis must be judged through that lens.

KEY EXPECTATIONS FOR THIS REVIEW:
• For EVERY held position: explicitly answer "Is the fundamental thesis still intact?"
  – YES: recommend HOLD or ADD — do not exit just because the stock hasn't moved.
  – NO (thesis broken): recommend EXIT with clear justification.
• The engine enforces a 10-trading-day minimum hold period.
  Do NOT recommend selling any position held less than 10 trading days unless
  unrealised loss > 25% or the thesis is conclusively broken.
• Think in months, not days. Short-term price noise is irrelevant for fundamental analysis.
• For candidates: rank by fundamental quality and long-term potential — not
  by short-term price movement.
• A position that holds steady and preserves capital is better than rapid churning.
  Every round-trip costs fees. Fewer, better trades win.
"""

HOLDING_DISCIPLINE = """
## HOLDING DISCIPLINE (ENGINE-ENFORCED)
The execution engine REJECTS sell orders for positions held fewer than
10 trading days, UNLESS unrealised loss > 25% or stop-loss was triggered.
Do NOT recommend exits for recently entered positions unless one of these
exceptions clearly applies. Instead, recommend monitoring or stop-loss adjustment.
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
   • Near-term catalysts (< 3 months): earnings, partnerships, product launches
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
## MONTHLY STRATEGY PLAN
After completing the fundamental analysis, provide a structured strategy plan:

### PORTFOLIO HEALTH SUMMARY
• Overall portfolio conviction (0.0–1.0) with justification
• Weakest holding: which position has the most fragile thesis and why?
• Strongest holding: which position has the best fundamental outlook?
• Cash allocation comment: is the current cash level appropriate?

### WATCHLIST PRIORITY RANKING
Rank the eligible candidates (≤ 100 EUR) from most to least attractive.
For each: company name, ticker, 2-sentence buy thesis, key risk.
Maximum 7 ranked candidates.

### POSITION REVIEW (THESIS-BASED — MANDATORY)
For EACH held position answer explicitly:
• Is the fundamental thesis still intact? YES / NO / UNCERTAIN
• If NO or UNCERTAIN: recommend EXIT ONLY if held ≥ 10 trading days AND
  justified by fundamental breakdown. Otherwise, recommend monitoring.
• If YES: recommend HOLD or ADD with target price and time horizon.
• Reminder: the 10-day engine rule cannot be bypassed — plan accordingly.

### POSITIONS TO WATCH CLOSELY NEXT MONTH
• Any position where stop-loss should be adjusted (with suggested new level)?
• Any position worth adding to on a price dip (with target entry zone)?
• Any position where the thesis is weakening but not yet broken?

### COMING WEEKS OUTLOOK
• Overall market environment (inferred from fundamentals + macro knowledge)
• Key company-specific events to monitor for held positions
• Any sector rotation signals visible in the candidate universe?
"""

CONTEXT_BLOCK = """
## CONTEXT
### Current Portfolio State
{portfolio}

### Recent Execution Log (last 4 weeks, including failed/rejected orders)
{execution_log}

### Account Overview
• Available cash : {cash:.2f} EUR
• Trading fee    : {commission:.2f} EUR per filled order (round-trip cost: {round_trip:.2f} EUR)
• MAX positions  : 7
• Min hold period: 10 trading days (engine-enforced)
"""

CANDIDATE_SECTION = """
## ELIGIBLE MARKET CANDIDATES (≤ 100 EUR / USD as of today)
The following stocks from the candidate universe currently trade below the price limit.
Analyse fundamentals for EVERY ticker listed — this is your research universe.
Only these tickers are eligible for new buys in the coming weeks.

{candidates}
"""

OUTPUT_FORMAT = """
## OUTPUT FORMAT (STRICT)
Produce exactly three tagged blocks — no other text outside these blocks:

<FUNDAMENTAL_ANALYSIS>
### HELD POSITIONS
[Full 6-area analysis for each held position]

### WATCHLIST CANDIDATES
[Full 6-area analysis for each candidate ≤ 100 EUR]
</FUNDAMENTAL_ANALYSIS>

<WATCHLIST_RECOMMENDATION>
[Complete monthly strategy plan as specified in MONTHLY STRATEGY PLAN above]
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

    if portfolio.empty:
        portfolio_text = (
            f"  No active positions.\n"
            f"  Available cash: {cash:.2f} EUR\n"
            f"  This is a FRESH portfolio — focus your analysis on the best candidates\n"
            f"  to initiate in the coming week. Rank your top 7 picks with full justification."
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

    execution_log = libb.recent_execution_logs()
    if isinstance(execution_log, str):
        execution_log_text = execution_log if execution_log.strip() else "No recent trade logs."
    elif not execution_log.empty:
        execution_log_text = execution_log.to_string(index=False)
    else:
        execution_log_text = "No recent trade logs."

    already_held = list(portfolio["ticker"].str.upper()) if not portfolio.empty else []
    candidates_text = get_market_candidates(today, price_limit=100.0, already_held=already_held)

    return (
        SYSTEM_HEADER.format(today=today)
        + PURPOSE
        + INVESTOR_MINDSET
        + HOLDING_DISCIPLINE
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
