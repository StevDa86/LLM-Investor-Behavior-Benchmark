"""
LLM-IBB Dashboard
Run: py dashboard.py  ->  http://0.0.0.0:5000
Accessible from any device in the network (e.g. Armbian server).
"""
import json, csv, logging, math, threading
from collections import deque
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, render_template, abort, request
from libb.other.key_store import get_masked_keys, set_key, delete_key
from user_side.prompt_orchestration.get_prompt_data import resolve_ticker_names

# Werkzeug-Access-Log auf Fehler/Warnungen beschränken (keine GET /api/... 200-Zeilen)
logging.getLogger("werkzeug").setLevel(logging.WARNING)
app = Flask(__name__)
RUNS_BASE = Path("user_side/runs/run_v1")

# background workflow state
_workflow_lock = threading.Lock()
_workflow_running = False
_workflow_error: str | None = None

# background backtest state
_backtest_lock = threading.Lock()
_backtest_running = False
_backtest_error: str | None = None
_backtest_log: deque = deque(maxlen=500)
_backtest_cancel = threading.Event()

# background workflow log
_workflow_log: deque = deque(maxlen=500)


def append_backtest_log(msg: str) -> None:
    """Thread-safe: timestamped log line in den Puffer schreiben."""
    ts = datetime.now().strftime("%H:%M:%S")
    _backtest_log.append(f"[{ts}] {msg}")
    print(msg)  # weiterhin auch auf dem Server sichtbar


def append_workflow_log(msg: str) -> None:
    """Thread-safe: timestamped log line in den Workflow-Puffer schreiben."""
    ts = datetime.now().strftime("%H:%M:%S")
    _workflow_log.append(f"[{ts}] {msg}")
    print(msg)
def _sanitize_floats(obj):
    """Replace NaN/Inf float values with None (JSON null) recursively.
    Python's json module emits non-standard NaN/Infinity literals that
    browsers cannot parse – this ensures strictly valid JSON."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_floats(v) for v in obj]
    return obj

def get_runs():
    if not RUNS_BASE.exists():
        return []
    return sorted(d.name for d in RUNS_BASE.iterdir() if d.is_dir())
def run_dir(run):
    p = RUNS_BASE / run
    if not p.exists():
        abort(404)
    return p
def read_json(path):
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return _sanitize_floats(json.load(f))
def read_csv(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def dedup_history_by_date(rows: list[dict]) -> list[dict]:
    """Dedupliziert portfolio_history auf einen Eintrag pro Tag (letzter Eintrag gewinnt).
    Gibt die Ergebnisse chronologisch sortiert zurück."""
    seen: dict[str, dict] = {}
    for row in rows:
        d = row.get("date", "")
        if d:
            seen[d] = row          # späterer Eintrag überschreibt früheren
    return sorted(seen.values(), key=lambda r: r.get("date", ""))
def overview_for(run):
    p         = RUNS_BASE / run
    cash_data = read_json(p / "portfolio" / "cash.json")
    history   = read_csv(p / "portfolio" / "portfolio_history.csv")
    equity = cash = float(cash_data.get("cash", 0))
    total_return = 0.0
    daily_return = None
    if history:
        last         = history[-1]
        equity       = float(last.get("equity") or equity)
        cash         = float(last.get("cash") or cash)
        total_return = float(last.get("overall_return_pct") or 0)
        dr = last.get("daily_return_pct")
        daily_return = float(dr) if dr not in (None, "", "None") else None
    logs_dir = p / "logging"
    last_log = {}
    if logs_dir.exists():
        files = sorted(logs_dir.glob("*.json"), reverse=True)
        if files:
            last_log = read_json(files[0])
    # Sum unrealized PnL across all open positions
    positions = read_csv(p / "portfolio" / "portfolio.csv")
    total_unrealized_pnl = 0.0
    for pos in positions:
        v = pos.get("unrealized_pnl")
        if v not in (None, "", "None"):
            try:
                total_unrealized_pnl += float(v)
            except (ValueError, TypeError):
                pass
    return {
        "run": run, "equity": equity, "cash": cash,
        "total_return_pct": total_return, "daily_return_pct": daily_return,
        "positions_count": len(positions),
        "total_unrealized_pnl": total_unrealized_pnl,
        "trades_count":    len(read_csv(p / "portfolio" / "trade_log.csv")),
        "last_log": last_log,
    }
@app.route("/")
def index():
    return render_template("index.html")
@app.route("/api/runs")
def api_runs():
    return jsonify(get_runs())
@app.route("/api/compare")
def api_compare():
    return jsonify({r: {"overview": overview_for(r),
                        "history": dedup_history_by_date(
                            read_csv(RUNS_BASE / r / "portfolio" / "portfolio_history.csv"))}
                    for r in get_runs()})
@app.route("/api/<run>/overview")
def api_overview(run):
    return jsonify(overview_for(run))
@app.route("/api/<run>/history")
def api_history(run):
    return jsonify(dedup_history_by_date(
        read_csv(run_dir(run) / "portfolio" / "portfolio_history.csv")))
@app.route("/api/<run>/positions")
def api_positions(run):
    return jsonify(read_csv(run_dir(run) / "portfolio" / "portfolio.csv"))
@app.route("/api/<run>/trades")
def api_trades(run):
    return jsonify(read_csv(run_dir(run) / "portfolio" / "trade_log.csv"))
@app.route("/api/<run>/sentiment")
def api_sentiment(run):
    data = read_json(run_dir(run) / "metrics" / "sentiment.json")
    return jsonify(data if isinstance(data, list) else [])
@app.route("/api/<run>/performance")
def api_performance(run):
    return jsonify(read_json(run_dir(run) / "metrics" / "performance.json"))
@app.route("/api/<run>/behavior")
def api_behavior(run):
    return jsonify(read_json(run_dir(run) / "metrics" / "behavior.json"))
@app.route("/api/<run>/reports")
def api_reports(run):
    p = run_dir(run)
    out = []
    for folder in ["daily_reports", "deep_research"]:
        d = p / "research" / folder
        if d.exists():
            for f in d.glob("*.txt"):
                out.append({"name": f.name, "type": folder})
    # Datum aus Dateiname extrahieren (Format: "xxx - YYYY-MM-DD - slot.txt")
    # und global absteigend sortieren → neueste zuerst
    def _sort_key(entry):
        parts = entry["name"].split(" - ")
        date_str = parts[1] if len(parts) >= 2 else ""
        slot_str = parts[2].replace(".txt", "") if len(parts) >= 3 else ""
        return (date_str, slot_str)
    out.sort(key=_sort_key, reverse=True)
    return jsonify(out)
@app.route("/api/<run>/report")
def api_report_content(run):
    p     = run_dir(run)
    rtype = request.args.get("type", "")
    rname = request.args.get("name", "")
    if rtype not in ("daily_reports", "deep_research") or not rname.endswith(".txt"):
        abort(400)
    fp = p / "research" / rtype / rname
    if not fp.exists():
        abort(404)
    return fp.read_text(encoding="utf-8"), 200, {"Content-Type": "text/plain; charset=utf-8"}
@app.route("/api/<run>/logs")
def api_logs(run):
    logs_dir = run_dir(run) / "logging"
    if not logs_dir.exists():
        return jsonify([])
    return jsonify([read_json(f) for f in sorted(logs_dir.glob("*.json"), reverse=True)])

@app.route("/api/ticker-names", methods=["POST"])
def api_ticker_names():
    """Resolve a list of ticker symbols to human-readable company names.
    Body: { "tickers": ["NOKIA.HE", "VOD.L", ...] }
    Returns: { "NOKIA.HE": "Nokia Corporation", ... }
    """
    data = request.get_json(silent=True) or {}
    tickers = data.get("tickers", [])
    if not isinstance(tickers, list):
        return jsonify({"error": "tickers must be a list"}), 400
    try:
        names = resolve_ticker_names([str(t) for t in tickers])
        return jsonify(names)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/run-workflow", methods=["POST"])
def api_run_workflow():
    global _workflow_running, _workflow_error
    with _workflow_lock:
        if _workflow_running:
            return jsonify({"ok": False, "message": "Workflow is already running"}), 409
        _workflow_running = True
        _workflow_error = None
        _workflow_log.clear()

    def _run():
        global _workflow_running, _workflow_error
        try:
            from user_side.workflow import main
            main(log_fn=append_workflow_log)
        except Exception as e:
            _workflow_error = str(e)
            append_workflow_log(f"[FEHLER] {e}")
        finally:
            _workflow_running = False

    threading.Thread(target=_run, daemon=True, name="workflow-manual").start()
    return jsonify({"ok": True, "message": "Workflow started in background"})

@app.route("/api/workflow-status")
def api_workflow_status():
    return jsonify({"running": _workflow_running, "error": _workflow_error})

@app.route("/api/run-backtest", methods=["POST"])
def api_run_backtest():
    global _backtest_running, _backtest_error
    with _backtest_lock:
        if _backtest_running:
            return jsonify({"ok": False, "message": "Backtest is already running"}), 409
        if _workflow_running:
            return jsonify({"ok": False, "message": "Cannot start backtest while workflow is running"}), 409
        _backtest_running = True
        _backtest_error = None
        _backtest_log.clear()
        _backtest_cancel.clear()

    data = request.get_json(silent=True) or {}
    start = data.get("start") or None
    end   = data.get("end")   or None
    reset = bool(data.get("reset", False))
    run   = (data.get("run") or "").strip()

    if not run or run not in get_runs():
        return jsonify({"ok": False, "message": f"Unbekannter Run: '{run}'. Bitte einen gültigen Run auswählen."}), 400

    run_dir = f"user_side/runs/run_v1/{run}"

    def _run():
        global _backtest_running, _backtest_error
        try:
            from user_side.backtesting_workflow import smallcap_backtest
            smallcap_backtest(
                run_dir=run_dir,
                start=start,
                end=end,
                reset_on_start=reset,
                log_fn=append_backtest_log,
                cancel_event=_backtest_cancel,
            )
        except Exception as e:
            _backtest_error = str(e)
            append_backtest_log(f"[FEHLER] {e}")
        finally:
            _backtest_running = False

    threading.Thread(target=_run, daemon=True, name="backtest-manual").start()
    return jsonify({"ok": True, "message": "Backtest started in background"})

@app.route("/api/backtest-status")
def api_backtest_status():
    return jsonify({"running": _backtest_running, "error": _backtest_error})

@app.route("/api/backtest-log")
def api_backtest_log():
    return jsonify({"lines": list(_backtest_log)})

@app.route("/api/workflow-log")
def api_workflow_log():
    return jsonify({"lines": list(_workflow_log)})

@app.route("/api/next-runs")
def api_next_runs():
    """Return the next 5 scheduled workflow run times (local time).

    Weekdays (Mo–Fr): 09:00 morning | 16:00 midday | 18:00 evening | 22:00 night (Deep Research)
    Saturday        : 10:00 weekend (Fundamental Review)
    Sunday          : no runs
    """
    from datetime import timedelta

    WEEKDAY_SCHEDULE = [
        ("09:00", "morning"),
        ("12:00", "noon"),
        ("16:00", "midday"),
        ("18:00", "evening"),
        ("22:00", "night"),
    ]
    SATURDAY_SCHEDULE = [("10:00", "weekend")]
    MAX_RESULTS = 5

    now = datetime.now()
    result = []

    for day_offset in range(10):
        candidate = now + timedelta(days=day_offset)
        weekday = candidate.weekday()

        if weekday == 6:          # Sunday – skip entirely
            continue
        elif weekday == 5:        # Saturday – fundamental review only
            day_schedule = SATURDAY_SCHEDULE
        else:                     # Mon–Fri – all trading + nightly slots
            day_schedule = WEEKDAY_SCHEDULE

        for time_str, slot_name in day_schedule:
            h, m = map(int, time_str.split(":"))
            scheduled = candidate.replace(hour=h, minute=m, second=0, microsecond=0)
            if scheduled > now:
                result.append({
                    "datetime": scheduled.strftime("%Y-%m-%d %H:%M"),
                    "slot": slot_name,
                    "weekday": scheduled.strftime("%A"),
                })
            if len(result) >= MAX_RESULTS:
                break
        if len(result) >= MAX_RESULTS:
            break

    return jsonify(result)

@app.route("/api/cancel-backtest", methods=["POST"])
def api_cancel_backtest():
    if not _backtest_running:
        return jsonify({"ok": False, "message": "Kein Backtest läuft"}), 409
    _backtest_cancel.set()
    append_backtest_log("[ABBRUCH] Abbruch angefordert – wird beim nächsten Checkpoint gestoppt …")
    return jsonify({"ok": True, "message": "Abbruch wird ausgeführt …"})


@app.route("/api/<run>/reset", methods=["POST"])
def api_reset_run(run):
    """Delete all artifacts for a run and recreate the empty file structure."""
    if run not in get_runs():
        return jsonify({"ok": False, "message": f"Unbekannter Run: '{run}'"}), 404
    with _workflow_lock:
        if _workflow_running:
            return jsonify({"ok": False, "message": "Workflow läuft – Reset nicht möglich"}), 409
    with _backtest_lock:
        if _backtest_running:
            return jsonify({"ok": False, "message": "Backtest läuft – Reset nicht möglich"}), 409
    try:
        from libb import LIBBmodel
        libb = LIBBmodel(f"user_side/runs/run_v1/{run}")
        libb.reset_run(cli_check=False, auto_ensure=True)
        return jsonify({"ok": True, "message": f"Run '{run}' wurde zurückgesetzt."})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500


# ─── Settings – API key management ────────────────────────────────────────────

@app.route("/api/settings/keys", methods=["GET"])
def api_settings_get_keys():
    """Return all known keys with masked values (plaintext never leaves the server)."""
    return jsonify(get_masked_keys())


@app.route("/api/settings/keys", methods=["POST"])
def api_settings_set_key():
    """Save (or update) an API key in the encrypted store and inject into os.environ."""
    data  = request.get_json(silent=True) or {}
    name  = (data.get("name")  or "").strip()
    value = (data.get("value") or "").strip()
    if not name or not value:
        return jsonify({"ok": False, "message": "name and value are required"}), 400
    try:
        set_key(name, value)
        return jsonify({"ok": True, "message": f"{name} saved successfully."})
    except Exception as exc:
        return jsonify({"ok": False, "message": str(exc)}), 500


@app.route("/api/settings/keys/<name>", methods=["DELETE"])
def api_settings_delete_key(name):
    """Delete an API key from the encrypted store."""
    try:
        deleted = delete_key(name)
        if not deleted:
            return jsonify({"ok": False, "message": "Key not found in store"}), 404
        return jsonify({"ok": True, "message": f"{name} deleted."})
    except Exception as exc:
        return jsonify({"ok": False, "message": str(exc)}), 500


if __name__ == "__main__":
    # Fehlende Run-Verzeichnisse für alle konfigurierten Modelle anlegen
    try:
        from user_side.workflow import MODELS
        from libb import LIBBmodel
        for model in MODELS:
            run_path = RUNS_BASE / model
            if not run_path.exists():
                LIBBmodel(str(run_path))
                print(f"[Bootstrap] Run-Verzeichnis für '{model}' erstellt.")
    except Exception as exc:
        print(f"[Bootstrap] Warnung: {exc}")

    print("LLM-IBB Dashboard -> http://0.0.0.0:5000")
    # host=0.0.0.0 makes the server reachable from other devices (e.g. Armbian)
    app.run(host="0.0.0.0", port=5000, debug=False)
