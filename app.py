"""
LLM-IBB – Gesamtapp
====================
Startet den Web-Dashboard-Server UND führt den Trading-Workflow
automatisch mehrmals täglich (Mo–Fr, Lokalzeit) aus:
  09:00 → morning  |  12:00 → noon  |  16:00 → midday  |  18:00 → evening

Start:
    python app.py

Dann im Browser (von beliebigem Gerät im Netz):
    http://<IP-des-Armbian-Servers>:5000
"""

import threading
import time
import sys
import logging
import schedule
from pathlib import Path

# Werkzeug-Access-Log auf Fehler/Warnungen beschränken (keine GET /api/... 200-Zeilen)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

# Projektwurzel im Suchpfad sicherstellen
sys.path.insert(0, str(Path(__file__).parent))

# API-Keys aus verschlüsseltem Store in os.environ laden (vor allem anderen)
from libb.other.key_store import load_into_environ
load_into_environ()

from dashboard import app, append_workflow_log  # Flask-App importieren


# ─── Bootstrap ────────────────────────────────────────────────────────────────

def bootstrap_runs() -> None:
    """Ensure every model in MODELS has its run directory initialised on disk.

    LIBBmodel.__init__ calls ensure_file_system() which creates all required
    subdirectories and seed files.  We only do this for models whose directory
    does not yet exist so we never overwrite existing data.
    """
    from user_side.workflow import MODELS
    from libb import LIBBmodel

    runs_base = Path("user_side/runs/run_v1")
    for model in MODELS:
        run_path = runs_base / model
        if not run_path.exists():
            try:
                LIBBmodel(str(run_path))
                print(f"[Bootstrap] Run-Verzeichnis für '{model}' erstellt.")
            except Exception as exc:
                print(f"[Bootstrap] Fehler beim Erstellen von '{model}': {exc}")
        else:
            print(f"[Bootstrap] '{model}' bereits vorhanden – übersprungen.")


# ─── Scheduler ────────────────────────────────────────────────────────────────

def run_workflow(slot: str):
    """Führt den Workflow für den angegebenen Slot aus (Hintergrundthread)."""
    try:
        append_workflow_log(f"[Scheduler] Starte Workflow [{slot}] …")
        from user_side.workflow import main
        main(slot=slot, log_fn=append_workflow_log)
        append_workflow_log(f"[Scheduler] Workflow [{slot}] erfolgreich abgeschlossen.")
    except Exception as e:
        append_workflow_log(f"[Scheduler] Fehler im Workflow [{slot}]: {e}")


def scheduler_loop():
    """Läuft als Daemon-Thread und prüft jede Minute auf fällige Tasks.

    WICHTIG: Für jede Tag/Zeit-Kombination muss schedule.every().<day> separat
    aufgerufen werden, da jeder Aufruf ein NEUES unabhängiges Job-Objekt erzeugt.
    Wird dasselbe Job-Objekt mehrfach mit .at().do() konfiguriert, überschreibt
    der letzte Aufruf alle vorherigen – nur der letzte Slot würde laufen!
    """
    # Tages-Trading-Slots (Börse geöffnet / aktiv)
    day_slots = [
        ("09:00", "morning"),
        ("12:00", "noon"),
        ("16:00", "midday"),
        ("18:00", "evening"),
    ]
    for time_str, slot in day_slots:
        schedule.every().monday.at(time_str).do(run_workflow, slot=slot)
        schedule.every().tuesday.at(time_str).do(run_workflow, slot=slot)
        schedule.every().wednesday.at(time_str).do(run_workflow, slot=slot)
        schedule.every().thursday.at(time_str).do(run_workflow, slot=slot)
        schedule.every().friday.at(time_str).do(run_workflow, slot=slot)

    # Nightly Deep Research – nach US-Börsenschluss, Mo–Fr 22:00
    schedule.every().monday.at("22:00").do(run_workflow, slot="night")
    schedule.every().tuesday.at("22:00").do(run_workflow, slot="night")
    schedule.every().wednesday.at("22:00").do(run_workflow, slot="night")
    schedule.every().thursday.at("22:00").do(run_workflow, slot="night")
    schedule.every().friday.at("22:00").do(run_workflow, slot="night")

    # Samstags-Fundamentalanalyse – einmal wöchentlich 10:00
    schedule.every().saturday.at("10:00").do(run_workflow, slot="weekend")

    print(
        "[Scheduler] Aktiv – "
        "Trading: Mo–Fr 09:00 / 12:00 / 16:00 / 18:00 | "
        "Deep Research: Mo–Fr 22:00 | "
        "Fundamental Review: Sa 10:00 (Lokalzeit)."
    )
    while True:
        schedule.run_pending()
        time.sleep(30)


# ─── Einstieg ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Fehlende Run-Verzeichnisse für alle konfigurierten Modelle anlegen
    bootstrap_runs()

    # Scheduler im Hintergrundthread starten
    scheduler_thread = threading.Thread(
        target=scheduler_loop, daemon=True, name="llm-ibb-scheduler"
    )
    scheduler_thread.start()

    HOST = "0.0.0.0"
    PORT = 5000

    print()
    banner_lines = [
        "LLM-IBB – Gesamtapp gestartet",
        f"Dashboard   :  http://{HOST}:{PORT}",
        "Trading     :  Mo–Fr  09:00 / 12:00 / 16:00 / 18:00",
        "Deep Res.   :  Mo–Fr  22:00  (nach US-Börsenschluss)",
        "Fundamental :  Sa     10:00  (Unternehmensanalyse)",
    ]
    inner_width = max(len(line) for line in banner_lines) + 2
    print("╔" + ("═" * inner_width) + "╗")
    for line in banner_lines:
        print(f"║ {line.ljust(inner_width - 2)} ║")
    print("╚" + ("═" * inner_width) + "╝")
    print()

    app.run(host=HOST, port=PORT, debug=False, threaded=True)

