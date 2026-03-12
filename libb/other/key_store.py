"""
Secure API key storage — Fernet symmetric encryption
=====================================================
Keys are stored encrypted in ``secrets.json`` next to the project root.
The encryption key lives in ``secrets.key``.

Both files are listed in .gitignore and must never be committed.

Usage
-----
    from libb.other.key_store import load_into_environ, set_key, delete_key, get_masked_keys

    load_into_environ()   # call once at app startup
"""

import os
import json
from pathlib import Path

from cryptography.fernet import Fernet

# ── Paths (project root = two levels above this file) ─────────────────────────
_BASE = Path(__file__).resolve().parents[2]
KEY_FILE   = _BASE / "secrets.key"
STORE_FILE = _BASE / "secrets.json"

# ── Catalogue of API keys the UI manages ──────────────────────────────────────
KNOWN_KEYS: list[dict] = [
    {
        "name":  "GROQ_API_KEY",
        "label": "Groq API Key",
        "hint":  "Free tier at console.groq.com — used for llama-3.3 / gemma2 models",
        "url":   "https://console.groq.com",
    },
    {
        "name":  "OPENAI_API_KEY",
        "label": "OpenAI API Key",
        "hint":  "Required for GPT-4.1 / o-series models",
        "url":   "https://platform.openai.com/api-keys",
    },
    {
        "name":  "DEEPSEEK_API_KEY",
        "label": "DeepSeek API Key",
        "hint":  "Required for DeepSeek-Chat / DeepSeek-R1 models",
        "url":   "https://platform.deepseek.com",
    },
]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_fernet() -> Fernet:
    """Return a Fernet cipher, generating and persisting a key on first run."""
    if not KEY_FILE.exists():
        KEY_FILE.write_bytes(Fernet.generate_key())
        try:
            KEY_FILE.chmod(0o600)   # owner-read-only on Unix/Linux
        except AttributeError:
            pass                    # Windows – silently skip chmod
    return Fernet(KEY_FILE.read_bytes())


def _load_store() -> dict[str, str]:
    """Decrypt and return the on-disk key store as {env_name: plaintext_value}."""
    if not STORE_FILE.exists():
        return {}
    fernet = _get_fernet()
    try:
        raw: dict[str, str] = json.loads(STORE_FILE.read_bytes())
        return {k: fernet.decrypt(v.encode()).decode() for k, v in raw.items()}
    except Exception as exc:
        print(f"[KeyStore] Could not decrypt store: {exc}")
        return {}


def _save_store(data: dict[str, str]) -> None:
    """Encrypt and persist the key store."""
    fernet = _get_fernet()
    encrypted = {k: fernet.encrypt(v.encode()).decode() for k, v in data.items()}
    STORE_FILE.write_text(json.dumps(encrypted, indent=2), encoding="utf-8")
    try:
        STORE_FILE.chmod(0o600)
    except AttributeError:
        pass


# ── Public API ────────────────────────────────────────────────────────────────

def load_into_environ() -> list[str]:
    """
    Decrypt all stored keys and inject them into ``os.environ``.

    Already-set environment variables are **not** overwritten so that
    manually exported keys (e.g. via ``$env:GROQ_API_KEY = "..."`` in
    PowerShell) always take precedence.

    Returns the list of key names that were actually loaded from the store.
    """
    store = _load_store()
    loaded: list[str] = []
    for name, value in store.items():
        if not os.environ.get(name):
            os.environ[name] = value
            loaded.append(name)
    if loaded:
        print(f"[KeyStore] Loaded {len(loaded)} API key(s) into environment: {', '.join(loaded)}")
    return loaded


def set_key(name: str, value: str) -> None:
    """Persist *value* for *name*, encrypted on disk, and apply to ``os.environ``."""
    if not name or not value:
        raise ValueError("name and value must not be empty")
    store = _load_store()
    store[name] = value
    _save_store(store)
    os.environ[name] = value


def delete_key(name: str) -> bool:
    """
    Remove *name* from the encrypted store and from ``os.environ``.

    Returns ``True`` if the key existed, ``False`` otherwise.
    """
    store = _load_store()
    if name not in store:
        return False
    del store[name]
    _save_store(store)
    os.environ.pop(name, None)
    return True


def get_masked_keys() -> list[dict]:
    """
    Return the list of known keys with status and a masked preview.

    The plaintext value is **never** returned to callers / the frontend.
    The ``masked`` field shows the first 6 and last 4 characters separated
    by bullets, e.g. ``gsk_ab••••••••••ef12``.
    """
    store   = _load_store()
    result  = []
    for meta in KNOWN_KEYS:
        name = meta["name"]
        # Prefer stored value; fall back to an already-set env var
        val  = store.get(name) or os.environ.get(name, "")
        if val and len(val) > 10:
            masked = val[:6] + "•" * (len(val) - 10) + val[-4:]
        elif val:
            masked = "•" * len(val)
        else:
            masked = ""
        result.append({
            "name":   name,
            "label":  meta["label"],
            "hint":   meta["hint"],
            "url":    meta["url"],
            "set":    bool(val),
            "masked": masked,
            # True only if the value comes from the encrypted store
            # (as opposed to a manually-set env var)
            "stored": name in store,
        })
    return result

