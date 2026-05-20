"""Einmaliges Fixskript: groq config.json und cash.json auf 1000 EUR setzen."""
import json
from pathlib import Path

base = Path("user_side/runs/run_v1/groq")

config = {"starting_cash": 1000.0, "commission": 1.0, "market_calendar": "NYSE"}
cash   = {"cash": 1000.0}

(base / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
(base / "portfolio" / "cash.json").write_text(json.dumps(cash, indent=2), encoding="utf-8")

print("groq/config.json  :", (base / "config.json").read_text())
print("groq/cash.json    :", (base / "portfolio" / "cash.json").read_text())
print("Done.")

