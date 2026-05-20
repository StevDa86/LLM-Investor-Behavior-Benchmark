from openai import OpenAI
import os
import re
import time
import threading
from ..prompts.deep_research_prompt import create_deep_research_prompt
from ..prompts.daily_research_prompt import create_daily_prompt
from ..prompts.fundamental_review_prompt import create_fundamental_review_prompt

# -------------------------------------------------------------------
# Groq free-tier model fallback list (ordered by quality).
# Each model has its own independent daily token quota:
#   llama-3.3-70b-versatile                  : 100 000 tokens/day  (best reasoning)
#   meta-llama/llama-4-scout-17b-16e-instruct: 500 000 tokens/day  (Llama 4, 5× quota)
#   llama-3.1-8b-instant                     : 500 000 tokens/day  (fast, lightweight)
# Source: https://console.groq.com/docs/rate-limits (Free Plan, 2026-03)
# -------------------------------------------------------------------
GROQ_FALLBACK_MODELS = [
    "llama-3.3-70b-versatile",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama-3.1-8b-instant",
]

_WAIT_RE = re.compile(r"try again in\s+(?:(\d+)m)?(?:\s*([\d.]+)s)?", re.IGNORECASE)


def _parse_retry_seconds(error_str: str) -> float | None:
    """Extract the 'Please try again in Xm Ys' wait time from a Groq error string."""
    m = _WAIT_RE.search(error_str)
    if not m:
        return None
    minutes = float(m.group(1) or 0)
    seconds = float(m.group(2) or 0)
    return minutes * 60 + seconds

def prompt_deepseek(text: str, model: str = "deepseek-chat") -> str:

    deepseek_client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",)
    
    response = deepseek_client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": text}],
        temperature=0.0,
    )

    if not response.choices:
        raise RuntimeError("No choices returned from DeepSeek.")

    content = response.choices[0].message.content
    if content is None:
        raise RuntimeError("Output from DeepSeek was None.")

    return content


def prompt_chatgpt(text: str, model: str = "gpt-4.1-mini") -> str:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": text}],
        temperature=0.0,
    )

    if not response.choices:
        raise RuntimeError("No choices returned from ChatGPT.")

    content = response.choices[0].message.content
    if content is None:
        raise RuntimeError("Output from ChatGPT was None.")

    return content

def prompt_openrouter(
    text: str,
    model: str = "openrouter/owl-alpha",
    log_fn=print,
    cancel_event: threading.Event | None = None,
) -> str:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY environment variable not set. "
            "Register at https://openrouter.ai/keys and set the key in Settings."
        )

    if cancel_event and cancel_event.is_set():
        raise InterruptedError("Backtest abgebrochen")

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://github.com/LLM-Investor-Behavior-Benchmark",
            "X-Title": "LLM-IBB",
        },
    )

    log_fn(f"  → OpenRouter [{model}] wird aufgerufen …")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": text}],
            temperature=0.0,
        )
    except Exception as e:
        raise RuntimeError(f"OpenRouter API error: {e}") from e

    if not response.choices:
        raise RuntimeError("No choices returned from OpenRouter.")

    content = response.choices[0].message.content
    if content is None:
        raise RuntimeError("Output from OpenRouter was None.")

    log_fn(f"  ✓ OpenRouter [{model}] Antwort erhalten.")
    return content


def prompt_gemini(
    text: str,
    model: str = "gemini-3.1-flash-lite-preview",
    log_fn=print,
    cancel_event: threading.Event | None = None,
) -> str:
    """
    Send a prompt to Google AI Studio via its OpenAI-compatible REST endpoint.

    Free-tier limits for Gemini 3.1 Flash Lite (as of 2026-03):
        15 RPM  |  250 000 TPM  |  500 RPD
    API key:  https://aistudio.google.com/apikey
    """
    api_key = os.environ.get("GOOGLE_AI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_AI_API_KEY environment variable not set. "
            "Kostenlosen API-Key unter https://aistudio.google.com/apikey erstellen "
            "und in den Einstellungen eintragen."
        )

    if cancel_event and cancel_event.is_set():
        raise InterruptedError("Backtest abgebrochen")

    client = OpenAI(
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )

    log_fn(f"  → Google AI Studio [{model}] wird aufgerufen …")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": text}],
            temperature=0.0,
        )
    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "quota" in error_str.lower() or "rate" in error_str.lower():
            raise RuntimeError(
                f"Google AI Studio Rate-Limit / Tages-Quota erschöpft: {e}. "
                "Quota-Übersicht: https://aistudio.google.com/plan_information"
            ) from e
        raise RuntimeError(f"Google AI Studio API error: {e}") from e

    if not response.choices:
        raise RuntimeError("No choices returned from Google AI Studio.")

    content = response.choices[0].message.content
    if content is None:
        raise RuntimeError("Output from Google AI Studio was None.")

    log_fn(f"  ✓ Google AI Studio [{model}] Antwort erhalten.")
    return content


def prompt_deep_research(libb, log_fn=print, cancel_event: threading.Event | None = None) -> str:
    model = libb._model_path.replace("user_side/runs/run_v1/", "")
    text = create_deep_research_prompt(libb)
    if model == "deepseek":
        return prompt_deepseek(text)
    elif model == "gpt-4.1":
        return prompt_chatgpt(text)
    elif model == "openrouter":
        return prompt_openrouter(text, log_fn=log_fn, cancel_event=cancel_event)
    elif model == "gemini":
        return prompt_gemini(text, log_fn=log_fn, cancel_event=cancel_event)
    else:
        return prompt_free_model(text, log_fn=log_fn, cancel_event=cancel_event)

def prompt_daily_report(libb, log_fn=print, cancel_event: threading.Event | None = None) -> str:
    model = libb._model_path.replace("user_side/runs/run_v1/", "")
    text = create_daily_prompt(libb)
    if model == "deepseek":
        return prompt_deepseek(text)
    elif model == "gpt-4.1":
        return prompt_chatgpt(text)
    elif model == "openrouter":
        return prompt_openrouter(text, log_fn=log_fn, cancel_event=cancel_event)
    elif model == "gemini":
        return prompt_gemini(text, log_fn=log_fn, cancel_event=cancel_event)
    else:
        return prompt_free_model(text, log_fn=log_fn, cancel_event=cancel_event)


def prompt_fundamental_review(libb, log_fn=print, cancel_event: threading.Event | None = None) -> str:
    """Saturday fundamental review – no orders, pure company & strategy analysis."""
    model = libb._model_path.replace("user_side/runs/run_v1/", "")
    text = create_fundamental_review_prompt(libb)
    if model == "deepseek":
        return prompt_deepseek(text)
    elif model == "gpt-4.1":
        return prompt_chatgpt(text)
    elif model == "openrouter":
        return prompt_openrouter(text, log_fn=log_fn, cancel_event=cancel_event)
    elif model == "gemini":
        return prompt_gemini(text, log_fn=log_fn, cancel_event=cancel_event)
    else:
        return prompt_free_model(text, log_fn=log_fn, cancel_event=cancel_event)


# -------------------------------------------------------------------
# FREE MODEL (Groq Cloud — no cost)
# -------------------------------------------------------------------

def prompt_free_model(
    text: str,
    models: list[str] | None = None,
    transient_retries: int = 2,
    short_limit_threshold_s: float = 90.0,
    log_fn=print,
    cancel_event: threading.Event | None = None,
) -> str:
    """
    Send a prompt to Groq's free-tier API with smart rate-limit handling.

    Strategy
    --------
    1. Try models in order (GROQ_FALLBACK_MODELS by default).
    2. On a decommissioned-model error: skip immediately to the next fallback.
    3. On a rate-limit error, parse the "Please try again in Xm Ys" wait time:
       - wait ≤ short_limit_threshold_s (default 90s):
             sleep that duration + 10s buffer, then retry the SAME model.
       - wait > short_limit_threshold_s (daily quota exhausted):
             switch immediately to the NEXT fallback model.
    4. On other transient errors: retry up to transient_retries times with
       exponential backoff (2 s, 4 s), then move to the next model.
    5. Raises RuntimeError only when ALL models in the list are exhausted.
    """
    if models is None:
        models = GROQ_FALLBACK_MODELS

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY environment variable not set. "
            "Register for free at https://console.groq.com and set the key."
        )

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )

    def _cancel_sleep(seconds: float) -> None:
        """Sleep in 0.5-s-Schritten, bricht ab wenn cancel_event gesetzt."""
        steps = int(seconds / 0.5)
        for _ in range(steps):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("Backtest abgebrochen")
            time.sleep(0.5)
        remainder = seconds - steps * 0.5
        if remainder > 0:
            time.sleep(remainder)

    for model_idx, model in enumerate(models):
        transient_attempt = 0
        while True:
            # Cancel-Check vor jedem Aufruf
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("Backtest abgebrochen")

            try:
                log_fn(f"  → Groq [{model}] wird aufgerufen …")
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": text}],
                    temperature=0.0,
                )
                if not response.choices:
                    raise RuntimeError(f"[{model}] No choices returned from Groq.")
                content = response.choices[0].message.content
                if content is None:
                    raise RuntimeError(f"[{model}] Groq returned None content.")
                log_fn(f"  ✓ Groq [{model}] Antwort erhalten.")
                return content

            except InterruptedError:
                raise
            except Exception as e:
                error_str = str(e)
                is_rate_limit = "429" in error_str or "rate_limit" in error_str.lower()
                is_decommissioned = "model_decommissioned" in error_str or "decommissioned" in error_str.lower()

                if is_decommissioned:
                    next_model = models[model_idx + 1] if model_idx + 1 < len(models) else None
                    log_fn(
                        f"  [Groq/{model}] Modell dekompissioniert – überspringe."
                        + (f" Weiter mit: {next_model}" if next_model else " Keine Fallbacks mehr.")
                    )
                    break

                elif is_rate_limit:
                    wait_s = _parse_retry_seconds(error_str)

                    if wait_s is not None and wait_s <= short_limit_threshold_s:
                        sleep_s = wait_s + 10
                        log_fn(
                            f"  [Groq/{model}] Rate-Limit – warte {sleep_s:.0f}s "
                            f"(Reset in {wait_s:.0f}s) …"
                        )
                        _cancel_sleep(sleep_s)
                        continue
                    else:
                        wait_desc = f"{wait_s:.0f}s" if wait_s else "unbekannt"
                        next_model = models[model_idx + 1] if model_idx + 1 < len(models) else None
                        if next_model:
                            log_fn(
                                f"  [Groq/{model}] Tages-Quota erschöpft "
                                f"(Retry in {wait_desc}). Wechsle zu: {next_model}"
                            )
                        break

                else:
                    transient_attempt += 1
                    if transient_attempt > transient_retries:
                        next_model = models[model_idx + 1] if model_idx + 1 < len(models) else None
                        if next_model:
                            log_fn(
                                f"  [Groq/{model}] Transient-Fehler nach "
                                f"{transient_retries} Retries: {e}. Weiter: {next_model}"
                            )
                        break
                    wait = 2 ** transient_attempt
                    log_fn(
                        f"  [Groq/{model}] Transient-Fehler – Retry in {wait}s "
                        f"(Versuch {transient_attempt}/{transient_retries}): {e}"
                    )
                    _cancel_sleep(wait)

    raise RuntimeError(
        f"Alle Groq-Modelle erschöpft: {models}. "
        "Tages-Token-Limits möglicherweise alle erreicht – morgen erneut versuchen oder "
        "upgraden: https://console.groq.com/settings/billing"
    )


