"""
LLM-IBB – Gesamtapp
====================
Startet den Web-Dashboard-Server UND führt den Trading-Workflow
automatisch nach Börsenschluss (Montag–Freitag, 21:45 UTC ≈ 16:45 ET) aus.

Start:
    python app.py

Dann im Browser (von beliebigem Gerät im Netz):
    http://<IP-des-Armbian-Servers>:5000
"""

import threading
import time
import sys
import schedule
from pathlib import Path

# Projektwurzel im Suchpfad sicherstellen
sys.path.insert(0, str(Path(__file__).parent))

# API-Keys aus verschlüsseltem Store in os.environ laden (vor allem anderen)
from libb.other.key_store import load_into_environ
load_into_environ()

from dashboard import app  # Flask-App importieren


# ─── Scheduler ────────────────────────────────────────────────────────────────

def run_workflow():
    """Führt den täglichen Workflow aus (wird im Hintergrundthread aufgerufen)."""
    try:
        print("[Scheduler] Starte Workflow …")
        from user_side.workflow import main
        main()
        print("[Scheduler] Workflow erfolgreich abgeschlossen.")
    except Exception as e:
        print(f"[Scheduler] Fehler im Workflow: {e}")


def scheduler_loop():
    """Läuft als Daemon-Thread und prüft jede Minute auf fällige Tasks."""
    # Workflow Mo–Fr um 21:45 UTC (≈ 16:45 ET = nach NYSE-Schluss)
    schedule.every().monday.at("21:45").do(run_workflow)
    schedule.every().tuesday.at("21:45").do(run_workflow)
    schedule.every().wednesday.at("21:45").do(run_workflow)
    schedule.every().thursday.at("21:45").do(run_workflow)
    schedule.every().friday.at("21:45").do(run_workflow)

    print("[Scheduler] Aktiv – Workflow läuft Mo–Fr um 21:45 UTC automatisch.")
    while True:
        schedule.run_pending()
        time.sleep(30)


# ─── Einstieg ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Scheduler im Hintergrundthread starten
    scheduler_thread = threading.Thread(
        target=scheduler_loop, daemon=True, name="llm-ibb-scheduler"
    )
    scheduler_thread.start()

    HOST = "0.0.0.0"
    PORT = 5000

    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║          LLM-IBB – Gesamtapp gestartet           ║")
    print(f"║  Dashboard:  http://{HOST}:{PORT}                  ║")
    print("║  Vom Netzwerk erreichbar über die IP dieses Hosts║")
    print("║  Scheduler:  Mo–Fr 21:45 UTC (nach NYSE-Schluss) ║")
    print("╚══════════════════════════════════════════════════╝")
    print()

    app.run(host=HOST, port=PORT, debug=False, threaded=True)
