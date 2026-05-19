"""Patch /opt/LLM-Investor-Behavior-Benchmark/app.py on the Armbian server:
Add a startup_catchup() function and call it after the scheduler thread starts.
"""
import sys

APP_PATH = "/opt/LLM-Investor-Behavior-Benchmark/app.py"

CATCHUP_FN = '''

# ─── Startup Catch-up ─────────────────────────────────────────────────────────

def startup_catchup() -> None:
    """Run any daily slot that was missed because the service restarted.

    The schedule library does not replay jobs that fired while the app was
    offline.  On startup we therefore check whether the current time falls
    within 30 minutes AFTER a scheduled slot and – if no report for that
    slot exists yet – trigger the workflow immediately in a background thread.
    Only weekday trading slots are considered (deep research and fundamental
    review are skipped here because they run late at night / on weekends and
    a restart in those windows is very unlikely to cause visible issues).
    """
    from datetime import datetime, timedelta
    from pathlib import Path

    now = datetime.now()
    if now.weekday() >= 5:          # Sat / Sun – nothing to catch up
        return

    TRADING_SLOTS = [
        ("09:00", "morning"),
        ("12:00", "noon"),
        ("16:00", "midday"),
        ("18:00", "evening"),
    ]
    CATCHUP_WINDOW_MINUTES = 30

    runs_base = Path("user_side/runs/run_v1")
    today_str = now.strftime("%Y-%m-%d")

    for time_str, slot in TRADING_SLOTS:
        h, m = map(int, time_str.split(":"))
        slot_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        deadline  = slot_dt + timedelta(minutes=CATCHUP_WINDOW_MINUTES)

        if not (slot_dt <= now <= deadline):
            continue  # outside the catch-up window for this slot

        try:
            from user_side.workflow import MODELS
        except Exception:
            break

        reports_exist = all(
            (runs_base / model / "research" / "daily_reports"
             / f"daily_update - {today_str} - {slot}.txt").exists()
            for model in MODELS
        )
        if reports_exist:
            append_workflow_log(
                f"[Startup Catch-up] Slot '{slot}' ({today_str}) bereits vorhanden "
                "– kein Nachstart noetig."
            )
            break

        append_workflow_log(
            f"[Startup Catch-up] Slot '{slot}' ({today_str}) wurde verpasst "
            "– starte nach ..."
        )
        threading.Thread(
            target=run_workflow,
            args=(slot,),
            daemon=True,
            name=f"startup-catchup-{slot}",
        ).start()
        break   # only one slot per startup

'''

MAIN_MARKER   = 'if __name__ == "__main__":'
SCHED_START   = "    scheduler_thread.start()"
CATCHUP_CALL  = (
    "\n\n    # Nachstart fuer verpasste Slots (Service-Neustart nach geplantem Zeitpunkt)\n"
    "    startup_catchup()"
)

content = open(APP_PATH, encoding="utf-8").read()

if "startup_catchup" in content:
    print("startup_catchup already present – nothing changed")
    sys.exit(0)

content = content.replace(MAIN_MARKER, CATCHUP_FN + MAIN_MARKER)
content = content.replace(SCHED_START, SCHED_START + CATCHUP_CALL)

open(APP_PATH, "w", encoding="utf-8").write(content)
print("OK – startup_catchup inserted")

