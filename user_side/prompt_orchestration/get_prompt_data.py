import yfinance as yf
import pandas as pd
from datetime import date

def truncate(text: str, limit: int):
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "..."

# -------------------------------------------------------------------
# TICKER → COMPANY NAME  (static lookup, yfinance fallback)
# -------------------------------------------------------------------
_TICKER_NAMES: dict[str, str] = {
    # Helsinki
    "NOKIA.HE":  "Nokia Corporation",
    "STERV.HE":  "Stora Enso Oyj R",
    "WRT1V.HE":  "Wärtsilä Oyj",
    "OUT1V.HE":  "Outokumpu Oyj",
    "FORTUM.HE": "Fortum Oyj",
    # XETRA Frankfurt
    "TUI1.DE":   "TUI AG",
    "NDA.DE":    "Nordea Bank",
    "FNTN.DE":   "freenet AG",
    "SDF.DE":    "K+S AG",
    "VOW.DE":    "Volkswagen AG Vz",
    "VOW3.DE":   "Volkswagen AG",
    "BMW.DE":    "BMW AG",
    "DBK.DE":    "Deutsche Bank AG",
    "LHA.DE":    "Lufthansa AG",
    "FRA.DE":    "Fraport AG",
    # Madrid
    "TEF.MC":    "Telefónica S.A.",
    # Paris
    "SES.PA":    "SES S.A.",
    "CGG.PA":    "CGG S.A.",
    "ORA.PA":    "Orange S.A.",
    # Milan
    "ENEL.MI":   "Enel S.p.A.",
    "TIT.MI":    "Telecom Italia S.p.A.",
    # London
    "VOD.L":     "Vodafone Group",
    "LLOY.L":    "Lloyds Banking Group",
    "BT-A.L":    "BT Group plc",
    # Amsterdam
    "PHIA.AS":   "Philips N.V.",
    # US
    "NOK":       "Nokia ADR (NYSE)",
    "F":         "Ford Motor Company",
    "VALE":      "Vale S.A.",
    "PLUG":      "Plug Power Inc.",
    "NIO":       "NIO Inc.",
    "XPEV":      "XPeng Inc.",
    "LCID":      "Lucid Group Inc.",
    "SNAP":      "Snap Inc.",
    "BBD":       "Banco Bradesco ADR",
    "ITUB":      "Itaú Unibanco ADR",
    "ABEV":      "Ambev S.A.",
    "SIRI":      "SiriusXM Holdings",
    "MARA":      "Marathon Digital Holdings",
    "SOFI":      "SoFi Technologies",
    "MAXN":      "Maxeon Solar Technologies",
    "IDEX":      "Ideanomics Inc.",
    "TLRY":      "Tilray Brands Inc.",
    "CLOV":      "Clover Health Investments",
    "WKHS":      "Workhorse Group Inc.",
    "NKLA":      "Nikola Corporation",
    "BCRX":      "BioCryst Pharmaceuticals",
    "RIOT":      "Riot Platforms Inc.",
}


def resolve_ticker_name(ticker: str) -> str:
    """Return the company name for a ticker.
    Uses the static map first; falls back to yfinance info if unknown.
    Never raises – returns the ticker symbol itself as last resort.
    """
    name = _TICKER_NAMES.get(ticker.upper()) or _TICKER_NAMES.get(ticker)
    if name:
        return name
    try:
        info = yf.Ticker(ticker).info
        name = info.get("shortName") or info.get("longName") or ticker
        return name
    except Exception:
        return ticker


def resolve_ticker_names(tickers: list[str]) -> dict[str, str]:
    """Bulk resolve ticker → name. Returns mapping for all requested tickers."""
    result: dict[str, str] = {}
    unknown: list[str] = []
    for t in tickers:
        static = _TICKER_NAMES.get(t.upper()) or _TICKER_NAMES.get(t)
        if static:
            result[t] = static
        else:
            unknown.append(t)
    # Fetch unknown names from yfinance one by one (keep it simple)
    for t in unknown:
        result[t] = resolve_ticker_name(t)
    return result


# -------------------------------------------------------------------
# CANDIDATE UNIVERSE  –  stocks that often trade ≤ 10 EUR / USD
# The list is intentionally broad; prices are verified at runtime.
# yfinance-format tickers only.
# -------------------------------------------------------------------
_CANDIDATE_UNIVERSE: list[str] = [
    # ── Helsinki (EUR) ──
    "NOKIA.HE",   # Nokia
    "STERV.HE",   # Stora Enso R
    "WRT1V.HE",   # Wärtsilä
    "OUT1V.HE",   # Outokumpu
    # ── XETRA Frankfurt (EUR) ──
    "TUI1.DE",    # TUI AG
    "NDA.DE",     # Nordea on XETR
    "FNTN.DE",    # freenet AG
    "SDF.DE",     # K+S AG
    # ── Euronext Paris (EUR) ──
    "TEF.MC",     # Telefonica (Madrid)
    # CGG.PA  → delisted / no market data
    # SES.PA  → delisted / no market data
    # ── Milan (EUR) ──
    "ENEL.MI",    # Enel
    "TIT.MI",     # Telecom Italia
    # ── London (GBP) ──
    "VOD.L",      # Vodafone
    "LLOY.L",     # Lloyds Banking
    "BT-A.L",     # BT Group
    # ── US NYSE / NASDAQ (USD) ──
    "NOK",        # Nokia ADR
    "F",          # Ford Motor
    "VALE",       # Vale SA
    "PLUG",       # Plug Power
    "NIO",        # NIO
    "XPEV",       # Xpeng Motors
    "LCID",       # Lucid Group
    "SNAP",       # Snap
    "BBD",        # Banco Bradesco ADR
    "ITUB",       # Itaú Unibanco
    "ABEV",       # Ambev ADR
    "SIRI",       # SiriusXM
    "MARA",       # Marathon Digital
    "SOFI",       # SoFi Technologies
    "TLRY",       # Tilray Brands
    # NKLA   → delisted / no price data
    "BCRX",       # BioCryst Pharmaceuticals
]


def get_market_candidates(
    run_date,
    price_limit: float = 10.0,
    already_held: list[str] | None = None,
) -> str:
    """
    Fetch prices for the candidate universe on *run_date* and return a
    formatted string listing only those stocks whose closing price is
    <= price_limit.  Already-held tickers are excluded from the
    suggestion list (the LLM already knows about them via the portfolio).

    Parameters
    ----------
    run_date : date | str | pd.Timestamp
        The trading date to fetch prices for.
    price_limit : float
        Maximum closing price. Default: 10.0.
    already_held : list[str] | None
        Tickers already in the portfolio (excluded from output).

    Returns
    -------
    str
        Formatted multi-line string, one stock per line:
        "  TICKER         Close:  X.XX"
    """
    from libb.execution.get_market_data import download_bulk_data_on_given_date

    held = {t.upper() for t in (already_held or [])}
    candidates = [t for t in _CANDIDATE_UNIVERSE if t.upper() not in held]

    run_ts = pd.Timestamp(run_date)
    fetch_date = run_ts.date()

    try:
        bulk = download_bulk_data_on_given_date(candidates, fetch_date)
    except Exception:
        bulk = {}

    # If empty (weekend / holiday / data not yet available) try previous day
    if not bulk:
        try:
            prev = (run_ts - pd.Timedelta(days=1)).date()
            bulk = download_bulk_data_on_given_date(candidates, prev)
        except Exception:
            pass

    if not bulk:
        return "  (Kursdaten momentan nicht verfuegbar – kein Kandidat abrufbar.)"

    rows: list[tuple[str, float]] = []
    for ticker, data in bulk.items():
        close = data.get("Close")
        if close is None:
            continue
        try:
            close = float(close)
        except (TypeError, ValueError):
            continue
        if close <= price_limit:
            rows.append((ticker, close))

    if not rows:
        return f"  (Kein Kandidat im Universum aktuell <= {price_limit:.2f} EUR/USD.)"

    rows.sort(key=lambda x: x[1])  # cheapest first
    lines = []
    for t, p in rows:
        name = _TICKER_NAMES.get(t.upper()) or _TICKER_NAMES.get(t) or t
        lines.append(f"  {t:<16} {name:<35} Close: {p:>7.2f}")
    return "\n".join(lines)

def get_macro_news(n: int = 3, summary_limit: int = 100):
    """
    Fetch and format broad market (macro) news using yfinance.

      CRITICAL LIMITATION 
    -------------------------
    This function ONLY returns news available on the CURRENT DAY.
    It relies on `yf.Ticker("^GSPC").news`, which is subject to Yahoo Finance
    backend limitations:
      - No access to historical macro news
      - No pagination or date filtering
      - Increasing `n` does NOT retrieve older articles
      - Headline availability is non-deterministic and may change over time

    Treat the output strictly as a real-time snapshot of market headlines.

    Parameters
    ----------
    n : int, optional
        Maximum number of macro news headlines to include from today's
        available set. Defaults to 5.

    summary_limit : int, optional
        Maximum number of characters to include in the truncated summary.
        Defaults to 200.

    Returns
    -------
    str
        A newline-separated string of formatted macro news items in the form:
        "<TITLE> - <TRUNCATED SUMMARY>".

    Notes
    -----
    Uses the S&P 500 index ("^GSPC") as a proxy for general market news.
    Yahoo Finance may return fewer items than requested or none at all.
    """
    ticker = yf.Ticker("^GSPC")
    news_headlines = ticker.news[:n]
    output = []
    for item in news_headlines:
        content = item.get("content", {})
        titles = content.get("title", "").strip()
        raw_summary = (
            content.get("summary")
            or item.get("summary")
            or ""  # Fallback if neither exists
        )
        summaries = truncate(raw_summary, summary_limit)
        output.append(f"{titles} - {summaries}")
    return "\n".join(output)