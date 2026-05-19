"""
reset_runs.py
=============
Einmaliges Skript zum Zurücksetzen aller LLM-Runs für einen Neustart.

Löscht alle Portfolio-, Metriken- und Research-Dateien für die drei Modelle
(groq, openrouter, gemini) und legt leere Verzeichnisstrukturen neu an.
Die neuen Konfigurationsparameter (starting_cash=1000, commission=1.0)
werden beim ersten Lauf automatisch durch workflow.py in config.json geschrieben.

Aufruf:
    python reset_runs.py
"""

import sys
from pathlib import Path

# ── Sicherstellen, dass das Projekt-Root im Python-Pfad liegt ──────────────
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libb import LIBBmodel

MODELS = ["groq", "openrouter", "gemini"]
STARTING_CASH = 1_000.0
COMMISSION    = 1.0

def reset_all(dry_run: bool = False) -> None:
    print("=" * 60)
    print("LLM-IBB Reset — Neustart der Runs")
    print(f"  starting_cash : {STARTING_CASH:.0f} EUR")
    print(f"  commission    : {COMMISSION:.2f} EUR")
    print(f"  modelle       : {', '.join(MODELS)}")
    print("=" * 60)

    if not dry_run:
        confirm = input("\nAlle Run-Daten werden unwiderruflich gelöscht. Fortfahren? (ja/nein): ").strip().lower()
        if confirm not in {"ja", "j", "yes", "y"}:
            print("Abgebrochen.")
            return

    for model in MODELS:
        run_path = f"user_side/runs/run_v1/{model}"
        print(f"\n  [{model}] Setze zurück: {run_path} …")
        try:
            libb = LIBBmodel(
                run_path,
                starting_cash=STARTING_CASH,
                commission=COMMISSION,
            )
            if dry_run:
                print(f"  [{model}] DRY RUN – nichts gelöscht.")
                continue
            libb.reset_run(cli_check=False, auto_ensure=True)
            print(f"  [{model}] ✓ Zurückgesetzt. Startkapital: {libb.cash:.2f} EUR")
        except Exception as e:
            print(f"  [{model}] ✗ Fehler: {e}")

    print("\n✓ Reset abgeschlossen. Starte workflow.py für den ersten Lauf.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("[DRY RUN] Keine Dateien werden gelöscht.\n")
    reset_all(dry_run=dry_run)

