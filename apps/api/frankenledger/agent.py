"""
FrankenLedger — agent layer, Spec 04.

Provides three jobs:
  - explain(flag)             -> {explanation, source}
  - draft_reply(order)        -> {draft, source}
  - structure(candidate_orders) -> {orders, source}

When a server-side LLM key is set (GEMINI_API_KEY or GROQ_API_KEY), the
agent makes a single HTTPS call (urllib, no SDK) per job with a strict
JSON-only prompt.  Invalid JSON from the LLM → deterministic fallback,
logged as such.  Timeout / rate-limit / any error → deterministic fallback;
the response marks the agent as unavailable.

When NO key is set → always deterministic mode.

Key rules (honesty):
  - The key is read from os.environ only; never logged, never returned.
  - The LLM only sees the current session's data passed into the call.
  - Agent output is always a suggestion; it never changes the ledger.
  - No fine-tuning is done or claimed.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from .draft import (
    explain_flag as _det_explain,
    draft_reply as _det_draft,
)
from .models import CandidateOrder

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mode detection
# ---------------------------------------------------------------------------

_GEMINI_KEY_VAR = "GEMINI_API_KEY"
_GROQ_KEY_VAR   = "GROQ_API_KEY"


def _get_provider() -> Optional[tuple[str, str]]:
    """
    Return (provider_name, api_key) if a key is configured, else None.
    The key value is NEVER logged.
    """
    gemini = os.environ.get(_GEMINI_KEY_VAR, "").strip()
    if gemini:
        return ("gemini", gemini)
    groq = os.environ.get(_GROQ_KEY_VAR, "").strip()
    if groq:
        return ("groq", groq)
    return None


def get_mode() -> dict:
    """
    Return {mode: "llm"|"deterministic", provider?: "gemini"|"groq"}.
    Never exposes the key value.
    """
    provider_info = _get_provider()
    if provider_info:
        return {"mode": "llm", "provider": provider_info[0]}
    return {"mode": "deterministic"}


# ---------------------------------------------------------------------------
# LLM HTTP calls (urllib only, no SDK)
# ---------------------------------------------------------------------------

_TIMEOUT_S = 20  # seconds per call

# Gemini — generateContent REST endpoint (AI Studio free tier)
_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent?key={key}"
)

# Groq — OpenAI-compatible chat completions
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_MODEL = "llama-3.1-8b-instant"  # free-tier model


def _call_gemini(api_key: str, prompt: str) -> str:
    """
    POST to Gemini generateContent.  Returns the raw text response.
    Raises on HTTP error / timeout.
    """
    url = _GEMINI_URL.format(key=urllib.parse.quote(api_key, safe=""))
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
        body = resp.read().decode()
    parsed = json.loads(body)
    # Extract text from Gemini's response structure
    return parsed["candidates"][0]["content"]["parts"][0]["text"]


def _call_groq(api_key: str, prompt: str) -> str:
    """
    POST to Groq chat completions (OpenAI-compatible).
    Returns the raw text response.  Raises on HTTP error / timeout.
    """
    payload = {
        "model": _GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a ledger assistant for a small shop. "
                    "Respond ONLY with valid JSON — no prose, no markdown."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        _GROQ_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
        body = resp.read().decode()
    parsed = json.loads(body)
    return parsed["choices"][0]["message"]["content"]


def _call_llm(provider: str, api_key: str, prompt: str) -> str:
    """Route to the correct provider."""
    if provider == "gemini":
        return _call_gemini(api_key, prompt)
    if provider == "groq":
        return _call_groq(api_key, prompt)
    raise ValueError(f"Unknown provider: {provider!r}")


def _parse_json_response(raw: str) -> dict:
    """
    Parse the LLM response as JSON.
    Raises ValueError if it is not valid JSON or not a dict.
    """
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop first and last fence lines
        inner = lines[1:-1] if lines[-1].startswith("```") else lines[1:]
        text = "\n".join(inner).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a JSON object, got {type(parsed).__name__}")
    return parsed


# ---------------------------------------------------------------------------
# Job prompts
# ---------------------------------------------------------------------------

def _explain_prompt(flag: dict) -> str:
    return (
        "You are a ledger assistant for a small kiryana shop in Pakistan. "
        "Explain this reconciliation flag in one plain-language sentence "
        "suitable for the shop owner. Use simple Roman Urdu/English mix. "
        "Cite the exact evidence (chat line number and ledger row number). "
        "Return ONLY a JSON object with a single key 'explanation' (string). "
        "Flag data: " + json.dumps(flag, ensure_ascii=False)
    )


def _draft_prompt(order: dict) -> str:
    return (
        "You are a ledger assistant for a small kiryana shop in Pakistan. "
        "Write a short WhatsApp message (1–2 sentences) in Roman Urdu/English "
        "mix to remind this customer of their unpaid balance. "
        "Be polite and friendly. "
        "Return ONLY a JSON object with a single key 'draft' (string). "
        "Order data: " + json.dumps(order, ensure_ascii=False)
    )


def _structure_prompt(candidate_orders: list[dict]) -> str:
    return (
        "You are a ledger assistant for a small kiryana shop in Pakistan. "
        "Review these candidate orders extracted from a WhatsApp chat. "
        "Return them as a JSON array under the key 'orders', "
        "with any obvious low-confidence corrections applied "
        "(e.g., fix a misspelled item name). "
        "Do NOT invent orders or change amounts. "
        "Return ONLY a JSON object: {\"orders\": [...]}. "
        "Candidate orders: " + json.dumps(candidate_orders, ensure_ascii=False)
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def explain(flag: dict) -> dict:
    """
    Explain a reconciliation flag.

    Returns:
      {explanation: str, source: "llm"|"template"}

    Falls back to a deterministic template if:
      - No LLM key is configured.
      - The LLM call fails (timeout, error, invalid JSON).
    """
    provider_info = _get_provider()

    if provider_info:
        provider, key = provider_info
        prompt = _explain_prompt(flag)
        try:
            raw = _call_llm(provider, key, prompt)
            parsed = _parse_json_response(raw)
            explanation = parsed.get("explanation", "")
            if not isinstance(explanation, str) or not explanation.strip():
                raise ValueError("Empty or invalid 'explanation' in LLM response")
            return {"explanation": explanation.strip(), "source": "llm"}
        except (urllib.error.URLError, TimeoutError) as exc:
            logger.warning("LLM call timed out or network error (%s); using deterministic fallback.", exc)
        except json.JSONDecodeError as exc:
            logger.warning("LLM returned invalid JSON (%s); using deterministic fallback.", exc)
        except ValueError as exc:
            logger.warning("LLM response validation failed (%s); using deterministic fallback.", exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM call failed (%s); using deterministic fallback.", exc)

    # Deterministic fallback
    explanation = _det_explain(flag)
    return {
        "explanation": explanation,
        "source": "template",
        "agent_note": "Deterministic mode — agent unavailable right now.",
    }


def draft_reply(order: dict) -> dict:
    """
    Draft a WhatsApp reply for an unpaid order.

    Returns:
      {draft: str, source: "llm"|"template"}

    Falls back to a deterministic template on any LLM failure.
    """
    provider_info = _get_provider()

    if provider_info:
        provider, key = provider_info
        prompt = _draft_prompt(order)
        try:
            raw = _call_llm(provider, key, prompt)
            parsed = _parse_json_response(raw)
            draft = parsed.get("draft", "")
            if not isinstance(draft, str) or not draft.strip():
                raise ValueError("Empty or invalid 'draft' in LLM response")
            return {"draft": draft.strip(), "source": "llm"}
        except (urllib.error.URLError, TimeoutError) as exc:
            logger.warning("LLM call timed out or network error (%s); using deterministic fallback.", exc)
        except json.JSONDecodeError as exc:
            logger.warning("LLM returned invalid JSON (%s); using deterministic fallback.", exc)
        except ValueError as exc:
            logger.warning("LLM response validation failed (%s); using deterministic fallback.", exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM call failed (%s); using deterministic fallback.", exc)

    # Deterministic fallback
    draft = _det_draft(order)
    return {
        "draft": draft,
        "source": "template",
        "agent_note": "Deterministic mode — agent unavailable right now.",
    }


def structure(candidate_orders: list[dict]) -> dict:
    """
    Attempt to structure / clean candidate orders with the LLM.

    Returns:
      {orders: [...], source: "llm"|"deterministic"}

    Falls back to returning the candidate orders as-is on any LLM failure.
    """
    provider_info = _get_provider()

    if provider_info:
        provider, key = provider_info
        prompt = _structure_prompt(candidate_orders)
        try:
            raw = _call_llm(provider, key, prompt)
            parsed = _parse_json_response(raw)
            orders = parsed.get("orders", None)
            if not isinstance(orders, list):
                raise ValueError("Expected 'orders' list in LLM response")
            return {"orders": orders, "source": "llm"}
        except (urllib.error.URLError, TimeoutError) as exc:
            logger.warning("LLM call timed out or network error (%s); using deterministic fallback.", exc)
        except json.JSONDecodeError as exc:
            logger.warning("LLM returned invalid JSON (%s); using deterministic fallback.", exc)
        except ValueError as exc:
            logger.warning("LLM response validation failed (%s); using deterministic fallback.", exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM call failed (%s); using deterministic fallback.", exc)

    # Deterministic fallback: return candidate orders as-is
    return {
        "orders": candidate_orders,
        "source": "deterministic",
        "agent_note": "Deterministic mode — agent unavailable right now.",
    }
