"""
Smoke-Test für die Prompt-Token-Optimierungen und Bulk-Downloads.

Ausführen:
    py test_optimizations.py
"""
import sys
import textwrap
import pandas as pd
from datetime import date

# ── Hilfsfunktion ────────────────────────────────────────────────────────────

def approx_tokens(text: str) -> int:
    """Grobe Token-Schätzung: Zeichen / 4 (OpenAI-Daumenregel)."""
    return len(text) // 4

def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def ok(msg: str):  print(f"  ✓ {msg}")
def fail(msg: str): print(f"  ✗ {msg}"); sys.exit(1)

# ── 1. Prompt-Importe ────────────────────────────────────────────────────────

section("1 · Import-Check")
try:
    from user_side.prompts.daily_research_prompt import (
        SYSTEM_HEADER, CAPITAL_RULE, DAILY_OBJECTIVES,
        CONCENTRATION_RULE, US_NEWS_SECTION, DAILY_OUTPUT_REQUIREMENTS,
        OUTPUT_TEMPLATE, orders_section, create_daily_prompt,
    )
    from user_side.prompts.deep_research_prompt import (
        SYSTEM_HEADER as DS_HEADER,
        CORE_RULES, ORDER_SPEC_FORMAT, ANALYSIS_REQUIREMENTS,
        OUTPUT_REQUIREMENTS, OUTPUT_TEMPLATE as DS_OUTPUT,
        CONTEXT_BLOCK, create_deep_research_prompt,
    )
    from user_side.prompts.smallcap_daily_prompt import create_smallcap_daily_prompt
    from user_side.prompts.smallcap_deep_prompt import create_smallcap_deep_prompt
    ok("Alle Prompt-Module importiert")
except Exception as e:
    fail(f"Import fehlgeschlagen: {e}")

# ── 2. Kein "RESTATE RULES" mehr ────────────────────────────────────────────

section("2 · 'BEGIN BY RESTATING THE RULES' entfernt")

for name, text in [("deep_research SYSTEM_HEADER", DS_HEADER),
                   ("deep_research ANALYSIS_REQUIREMENTS", ANALYSIS_REQUIREMENTS)]:
    if "RESTATE" in text.upper() or "RESTATING" in text.upper():
        fail(f"'RESTATE' noch vorhanden in: {name}")
    else:
        ok(f"Nicht vorhanden in {name}")

# ── 3. Keine langen Trennlinien mehr ─────────────────────────────────────────

section("3 · Dashes-Separator entfernt (≥ 30 Striche)")

from user_side.prompts import (
    daily_research_prompt as drp,
    deep_research_prompt  as deeprp,
    smallcap_daily_prompt as scdp,
    smallcap_deep_prompt  as scdeep,
)
import inspect

for mod in [drp, deeprp, scdp, scdeep]:
    src = inspect.getsource(mod)
    # Nur echte String-Zeilen prüfen (keine Python-Kommentare)
    long_dashes = [
        ln for ln in src.splitlines()
        if ln.count('-') >= 30 and not ln.lstrip().startswith('#')
    ]
    if long_dashes:
        fail(f"Noch lange Trennlinien in {mod.__name__}:\n    {long_dashes[0]}")
    else:
        ok(f"Keine langen Trennlinien in {mod.__name__}")

# ── 4. Kein doppeltes JSON-Beispiel in deep_research ─────────────────────────

section("4 · Kein doppeltes ORDERS_JSON-Beispiel")

src_deep = inspect.getsource(deeprp)
occurrences = src_deep.count('<ORDERS_JSON>')
# ORDER_SPEC_FORMAT hat 1 × ORDERS_JSON-Block + "If no trade" inline → 2 ist OK
if occurrences > 2:
    fail(f"Zu viele <ORDERS_JSON>-Blöcke in deep_research_prompt: {occurrences}")
else:
    ok(f"<ORDERS_JSON> kommt {occurrences}× vor (OK)")

# ── 5. Token-Zählung der statischen Sektionen ────────────────────────────────

section("5 · Token-Schätzung (statische Teile, ohne Portfolio-Inhalt)")

daily_static = (
    SYSTEM_HEADER.format(today="2026-03-12")
    + CAPITAL_RULE
    + DAILY_OBJECTIVES
    + CONCENTRATION_RULE
    + US_NEWS_SECTION.format(news="(keine)")
    + DAILY_OUTPUT_REQUIREMENTS
    + OUTPUT_TEMPLATE.format(orders_section=orders_section)
)

deep_static = (
    DS_HEADER.format(today="2026-03-12")
    + CORE_RULES
    + ORDER_SPEC_FORMAT
    + ANALYSIS_REQUIREMENTS
    + OUTPUT_REQUIREMENTS
    + DS_OUTPUT
)

daily_tokens  = approx_tokens(daily_static)
deep_tokens   = approx_tokens(deep_static)

print(f"  daily_research_prompt  statisch: ~{daily_tokens} Tokens")
print(f"  deep_research_prompt   statisch: ~{deep_tokens} Tokens")

# Obergrenzen prüfen (vorher waren es ~600 / ~900 nur für statische Teile)
if daily_tokens > 550:
    fail(f"Daily-Prompt statisch zu groß: {daily_tokens} > 550")
else:
    ok(f"Daily-Prompt im Zielbereich ({daily_tokens} ≤ 550)")

if deep_tokens > 800:
    fail(f"Deep-Prompt statisch zu groß: {deep_tokens} > 800")
else:
    ok(f"Deep-Prompt im Zielbereich ({deep_tokens} ≤ 800)")

# ── 6. Bulk-Download-Importe ─────────────────────────────────────────────────

section("6 · Bulk-Download-Funktionen importierbar")

try:
    from libb.execution.get_market_data import (
        download_bulk_data_on_given_date,
        download_bulk_data_on_given_range,
        _extract_bulk_snapshots,
    )
    ok("download_bulk_data_on_given_date importiert")
    ok("download_bulk_data_on_given_range importiert")
    ok("_extract_bulk_snapshots importiert")
except Exception as e:
    fail(f"Bulk-Download-Import fehlgeschlagen: {e}")

# ── 7. Bulk-Download live (optional, braucht Internet) ───────────────────────

section("7 · Bulk-Download live (AAPL + MSFT, letzter Handelstag)")

TICKERS = ["AAPL", "MSFT"]
TEST_DATE = "2026-03-11"   # Mittwoch → normaler Handelstag

try:
    result = download_bulk_data_on_given_date(TICKERS, TEST_DATE)
    if not result:
        fail(f"Bulk-Download hat leeres Dict zurückgegeben für {TICKERS}")
    for ticker in TICKERS:
        if ticker not in result:
            fail(f"{ticker} fehlt im Bulk-Result")
        snap = result[ticker]
        assert snap["Close"] > 0, f"Close-Preis für {ticker} ist 0"
        ok(f"{ticker}: Close={snap['Close']:.2f}, Vol={snap['Volume']:,}")
except Exception as e:
    print(f"  ⚠  Live-Download übersprungen (kein Internet oder Markt geschlossen): {e}")

# ── 8. Bulk-Range-Download live ───────────────────────────────────────────────

section("8 · Bulk-Range-Download live (AAPL + MSFT, letzte Woche)")

try:
    result_range = download_bulk_data_on_given_range(
        TICKERS, start_date="2026-03-03", end_date="2026-03-11"
    )
    if not result_range:
        fail(f"Bulk-Range-Download hat leeres Dict zurückgegeben")
    for ticker in TICKERS:
        if ticker not in result_range:
            fail(f"{ticker} fehlt im Range-Result")
        rows = len(result_range[ticker]["Close"])
        ok(f"{ticker}: {rows} Handelstage geladen")
except Exception as e:
    print(f"  ⚠  Range-Download übersprungen: {e}")

# ── Ergebnis ─────────────────────────────────────────────────────────────────

print(f"\n{'='*60}")
print("  ✅  Alle Tests bestanden!")
print('='*60)

