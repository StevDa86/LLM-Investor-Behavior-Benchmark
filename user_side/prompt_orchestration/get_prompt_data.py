import yfinance as yf
import pandas as pd

def truncate(text: str, limit: int):
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "..."

# -------------------------------------------------------------------
# TICKER → COMPANY NAME  (static lookup, yfinance fallback)
# -------------------------------------------------------------------
_TICKER_NAMES: dict[str, str] = {
    # ── Helsinki ──
    "NOKIA.HE":  "Nokia Corporation",
    "STERV.HE":  "Stora Enso Oyj R",
    "WRT1V.HE":  "Wärtsilä Oyj",
    "OUT1V.HE":  "Outokumpu Oyj",
    "FORTUM.HE": "Fortum Oyj",
    # ── XETRA Frankfurt ──
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
    "CBK.DE":    "Commerzbank AG",
    "ENR.DE":    "Siemens Energy AG",
    "DTE.DE":    "Deutsche Telekom AG",
    "EOAN.DE":   "E.ON SE",
    "VNA.DE":    "Vonovia SE",
    "FRE.DE":    "Fresenius SE & Co.",
    "BAS.DE":    "BASF SE",
    "BAYN.DE":   "Bayer AG",
    "CON.DE":    "Continental AG",
    "SZG.DE":    "Salzgitter AG",
    "TKA.DE":    "thyssenkrupp AG",
    "EVT.DE":    "Evotec SE",
    "AIXA.DE":   "Aixtron SE",
    "LXS.DE":    "LANXESS AG",
    "AT1.DE":    "Aroundtown SA",
    "DHER.DE":   "Delivery Hero SE",
    "SHL.DE":    "Siemens Healthineers AG",
    "MBG.DE":    "Mercedes-Benz Group AG",
    "PAH3.DE":   "Porsche Automobil Holding SE",
    "IFX.DE":    "Infineon Technologies AG",
    "HFG.DE":    "HelloFresh SE",
    "WCH.DE":    "Wacker Chemie AG",
    "G24.DE":    "Scout24 SE",
    "WAF.DE":    "Siltronic AG",
    "KBX.DE":    "Knorr-Bremse AG",
    "VBK.DE":    "Verbio SE",
    "HABA.DE":   "Hamborner REIT AG",
    "LEG.DE":    "LEG Immobilien SE",
    "GXI.DE":    "Gerresheimer AG",
    # ── Madrid ──
    "TEF.MC":    "Telefónica S.A.",
    "IAG.MC":    "International Airlines Group",
    "CABK.MC":   "CaixaBank S.A.",
    "BBVA.MC":   "BBVA S.A.",
    "SANT.MC":   "Banco Santander S.A.",
    # ── Paris ──
    "SES.PA":    "SES S.A.",
    "CGG.PA":    "CGG S.A.",
    "ORA.PA":    "Orange S.A.",
    "BNP.PA":    "BNP Paribas S.A.",
    "GLE.PA":    "Société Générale S.A.",
    "RNO.PA":    "Renault S.A.",
    "STLAP.PA":  "Stellantis N.V.",
    "CA.PA":     "Carrefour S.A.",
    "ENGI.PA":   "Engie S.A.",
    "ACA.PA":    "Crédit Agricole S.A.",
    "VIE.PA":    "Veolia Environnement S.A.",
    "FR.PA":     "Valeo S.A.",
    "ML.PA":     "Compagnie Générale des Établissements Michelin",
    "VK.PA":     "Vallourec S.A.",
    # ── Milan ──
    "ENEL.MI":   "Enel S.p.A.",
    "TIT.MI":    "Telecom Italia S.p.A.",
    "ENI.MI":    "Eni S.p.A.",
    "UCG.MI":    "UniCredit S.p.A.",
    "ISP.MI":    "Intesa Sanpaolo S.p.A.",
    "STM.MI":    "STMicroelectronics N.V.",
    "LDO.MI":    "Leonardo S.p.A.",
    # ── Amsterdam ──
    "PHIA.AS":   "Philips N.V.",
    "ING.AS":    "ING Groep N.V.",
    "ABN.AS":    "ABN AMRO Bank N.V.",
    "NN.AS":     "NN Group N.V.",
    "RAND.AS":   "Randstad N.V.",
    # ── London ──
    "VOD.L":     "Vodafone Group",
    "LLOY.L":    "Lloyds Banking Group",
    "BT-A.L":    "BT Group plc",
    "BARC.L":    "Barclays plc",
    "BP.L":      "BP plc",
    "ITV.L":     "ITV plc",
    "RR.L":      "Rolls-Royce Holdings plc",
    "CNA.L":     "Centrica plc",
    "NWG.L":     "NatWest Group plc",
    "AV.L":      "Aviva plc",
    "MKS.L":     "Marks and Spencer Group plc",
    "TSCO.L":    "Tesco plc",
    # ── US NYSE / NASDAQ ──
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
    "TLRY":      "Tilray Brands Inc.",
    "BCRX":      "BioCryst Pharmaceuticals",
    "RIOT":      "Riot Platforms Inc.",
    "INTC":      "Intel Corporation",
    "PFE":       "Pfizer Inc.",
    "T":         "AT&T Inc.",
    "RIVN":      "Rivian Automotive Inc.",
    "BABA":      "Alibaba Group Holding Ltd.",
    "JD":        "JD.com Inc.",
    "UBER":      "Uber Technologies Inc.",
    "WBD":       "Warner Bros. Discovery Inc.",
    "PARA":      "Paramount Global",
    "CCL":       "Carnival Corporation",
    "AAL":       "American Airlines Group Inc.",
    "UAL":       "United Airlines Holdings Inc.",
    "DAL":       "Delta Air Lines Inc.",
    "LUV":       "Southwest Airlines Co.",
    "BAC":       "Bank of America Corp.",
    "C":         "Citigroup Inc.",
    "KEY":       "KeyCorp",
    "PBR":       "Petróleo Brasileiro S.A. ADR",
    "ERIC":      "Telefonaktiebolaget LM Ericsson ADR",
    "GRAB":      "Grab Holdings Ltd.",
    "HOOD":      "Robinhood Markets Inc.",
    "AMC":       "AMC Entertainment Holdings Inc.",
    "MU":        "Micron Technology Inc.",
    "PLTR":      "Palantir Technologies Inc.",
    "WFC":       "Wells Fargo & Company",
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
    for t in unknown:
        result[t] = resolve_ticker_name(t)
    return result


# -------------------------------------------------------------------
# CANDIDATE UNIVERSE  –  stocks eligible for trading (price verified at runtime)
# Price limit is 100 EUR / USD. All tickers verified as actively traded.
# -------------------------------------------------------------------
_CANDIDATE_UNIVERSE: list[str] = [
    # ── Helsinki (EUR) ──
    "NOKIA.HE",   # Nokia
    "STERV.HE",   # Stora Enso R
    "WRT1V.HE",   # Wärtsilä
    "OUT1V.HE",   # Outokumpu
    "FORTUM.HE",  # Fortum
    # ── XETRA Frankfurt (EUR) ──
    "TUI1.DE",    # TUI AG
    "NDA.DE",     # Nordea
    "FNTN.DE",    # freenet AG
    "SDF.DE",     # K+S AG
    "VOW.DE",     # Volkswagen Vz
    "VOW3.DE",    # Volkswagen
    "BMW.DE",     # BMW AG
    "DBK.DE",     # Deutsche Bank
    "LHA.DE",     # Lufthansa
    "FRA.DE",     # Fraport
    "CBK.DE",     # Commerzbank
    "ENR.DE",     # Siemens Energy
    "DTE.DE",     # Deutsche Telekom
    "EOAN.DE",    # E.ON
    "VNA.DE",     # Vonovia
    "FRE.DE",     # Fresenius
    "BAS.DE",     # BASF
    "BAYN.DE",    # Bayer
    "CON.DE",     # Continental
    "SZG.DE",     # Salzgitter
    "TKA.DE",     # thyssenkrupp
    "EVT.DE",     # Evotec
    "AIXA.DE",    # Aixtron
    "LXS.DE",     # LANXESS
    "AT1.DE",     # Aroundtown
    "DHER.DE",    # Delivery Hero
    "SHL.DE",     # Siemens Healthineers
    "MBG.DE",     # Mercedes-Benz
    "PAH3.DE",    # Porsche Holding SE
    "IFX.DE",     # Infineon
    "HFG.DE",     # HelloFresh
    "WCH.DE",     # Wacker Chemie
    "G24.DE",     # Scout24
    "WAF.DE",     # Siltronic
    "KBX.DE",     # Knorr-Bremse
    "VBK.DE",     # Verbio
    "HABA.DE",    # Hamborner REIT
    "LEG.DE",     # LEG Immobilien
    "GXI.DE",     # Gerresheimer
    # ── Madrid (EUR) ──
    "TEF.MC",     # Telefonica
    "IAG.MC",     # IAG (Iberia/BA)
    "CABK.MC",    # CaixaBank
    "BBVA.MC",    # BBVA
    "SANT.MC",    # Santander
    # ── Euronext Paris (EUR) ──
    "ORA.PA",     # Orange
    "BNP.PA",     # BNP Paribas
    "GLE.PA",     # Société Générale
    "RNO.PA",     # Renault
    "STLAP.PA",   # Stellantis
    "CA.PA",      # Carrefour
    "ENGI.PA",    # Engie
    "ACA.PA",     # Crédit Agricole
    "VIE.PA",     # Veolia
    "FR.PA",      # Valeo
    "VK.PA",      # Vallourec
    # ── Milan (EUR) ──
    "ENEL.MI",    # Enel
    "TIT.MI",     # Telecom Italia
    "ENI.MI",     # Eni
    "UCG.MI",     # UniCredit
    "ISP.MI",     # Intesa Sanpaolo
    "STM.MI",     # STMicroelectronics
    "LDO.MI",     # Leonardo
    # ── Amsterdam (EUR) ──
    "PHIA.AS",    # Philips
    "ING.AS",     # ING Groep
    "ABN.AS",     # ABN AMRO
    "NN.AS",      # NN Group
    "RAND.AS",    # Randstad
    # ── London (GBP — price check is in GBp, limit ~8500 GBp ≈ 100 EUR) ──
    "VOD.L",      # Vodafone
    "LLOY.L",     # Lloyds Banking
    "BT-A.L",     # BT Group
    "BARC.L",     # Barclays
    "BP.L",       # BP
    "ITV.L",      # ITV
    "RR.L",       # Rolls-Royce
    "CNA.L",      # Centrica
    "NWG.L",      # NatWest
    "AV.L",       # Aviva
    "MKS.L",      # Marks & Spencer
    "TSCO.L",     # Tesco
    # ── US NYSE / NASDAQ (USD) ──
    "NOK",        # Nokia ADR
    "F",          # Ford Motor
    "VALE",       # Vale SA
    "PLUG",       # Plug Power
    "NIO",        # NIO
    "XPEV",       # Xpeng
    "LCID",       # Lucid Group
    "SNAP",       # Snap
    "BBD",        # Banco Bradesco ADR
    "ITUB",       # Itaú Unibanco
    "ABEV",       # Ambev ADR
    "SIRI",       # SiriusXM
    "MARA",       # Marathon Digital
    "SOFI",       # SoFi Technologies
    "TLRY",       # Tilray Brands
    "BCRX",       # BioCryst Pharma
    "RIOT",       # Riot Platforms
    "INTC",       # Intel
    "PFE",        # Pfizer
    "T",          # AT&T
    "RIVN",       # Rivian
    "BABA",       # Alibaba
    "JD",         # JD.com
    "UBER",       # Uber
    "WBD",        # Warner Bros. Discovery
    "PARA",       # Paramount Global
    "CCL",        # Carnival
    "AAL",        # American Airlines
    "UAL",        # United Airlines
    "DAL",        # Delta Air Lines
    "LUV",        # Southwest Airlines
    "BAC",        # Bank of America
    "C",          # Citigroup
    "KEY",        # KeyCorp
    "PBR",        # Petrobras ADR
    "ERIC",       # Ericsson ADR
    "GRAB",       # Grab Holdings
    "HOOD",       # Robinhood
    "AMC",        # AMC Entertainment
    "MU",         # Micron Technology
    "PLTR",       # Palantir
    "WFC",        # Wells Fargo
]


def get_market_candidates(
    run_date,
    price_limit: float = 100.0,
    already_held: list[str] | None = None,
) -> str:
    """
    Fetch prices for the candidate universe on *run_date* and return a
    formatted string listing only those stocks whose closing price is
    <= price_limit (default: 100 EUR/USD).
    Already-held tickers are excluded (the LLM already knows them via the portfolio).
    """
    from libb.execution.get_market_data import download_bulk_data_on_given_date

    held = {t.upper() for t in (already_held or [])}
    candidates = [t for t in _CANDIDATE_UNIVERSE if t.upper() not in held]

    run_ts = pd.Timestamp(run_date)
    if pd.isna(run_ts):
        return "  (Ungültiges run_date – kein Kandidat abrufbar.)"
    fetch_date = str(run_ts.date())

    try:
        bulk = download_bulk_data_on_given_date(candidates, fetch_date)
    except Exception:
        bulk = {}

    # If empty (weekend / holiday / data not yet available) try previous day
    if not bulk:
        try:
            prev = str((run_ts - pd.Timedelta(days=1)).date())
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
        return f"  (Kein Kandidat im Universum aktuell <= {price_limit:.0f} EUR/USD.)"

    rows.sort(key=lambda x: x[1])  # cheapest first
    lines = []
    for t, p in rows:
        name = _TICKER_NAMES.get(t.upper()) or _TICKER_NAMES.get(t) or t
        lines.append(f"  {t:<16} {name:<40} Close: {p:>8.2f}")
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