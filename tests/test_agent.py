"""
tests/test_agent.py — Spec 04 agent-layer tests.

Covers:
  1. Deterministic mode (no key set) — all four endpoints return HTTP 200
     with source = "template" or "deterministic".
  2. GET /api/agent/status — returns mode="deterministic" and a label when
     no key is configured.
  3. POST /api/agent/explain — template source, explanation links to evidence.
  4. POST /api/agent/draft-reply — template source, draft contains Roman
     Urdu/English mix and the customer name.
  5. POST /api/agent/structure — deterministic source, orders returned as-is.
  6. Invalid-LLM-response fallback — simulate a bad LLM response and confirm
     the agent falls back to deterministic mode gracefully.
  7. Key-safety — no API key value appears in any response or log output.
  8. draft.explain_flag — template explanations for all five flag kinds.
  9. draft.draft_reply — template drafts for various order shapes.
 10. agent.get_mode — reflects actual env-var state.

Run from repo root:
  apps/api/.venv/bin/python -m pytest tests/test_agent.py -v
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import sys
import unittest.mock as mock

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps" / "api"))

# ---------------------------------------------------------------------------
# Ensure no real LLM key is present for the whole module
# (the env-var is patched per-test where needed)
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _no_llm_key(monkeypatch):
    """Strip any LLM keys from the environment for every test in this file."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)


# ---------------------------------------------------------------------------
# Imports (after sys.path tweak)
# ---------------------------------------------------------------------------
from frankenledger import agent as agent_module
from frankenledger.draft import explain_flag, draft_reply as draft_reply_fn

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_flag(
    kind: str = "UNMATCHED_ORDER",
    sender: str = "Ahmed",
    item: str = "cheeni",
    amount: float = 500.0,
    source_line: int = 6,
    row_index: int = 1,
    explanation: str = "",
) -> dict:
    return {
        "flag_id": "test-flag-id",
        "kind": kind,
        "chat_order": {
            "date": "2026-11-03",
            "sender": sender,
            "item": item,
            "item_raw": item,
            "quantity": 2.0,
            "unit": "kg",
            "amount_pkr": amount,
            "payment_status": "unknown",
            "source_line": source_line,
            "confidence": "high",
        },
        "ledger_rows": [
            {
                "row_index": row_index,
                "date": "2026-11-03",
                "customer": sender,
                "item": item,
                "quantity": "2kg",
                "amount_pkr": amount,
                "paid": False,
            }
        ],
        "explanation": explanation,
        "fix_description": "Add a ledger row.",
        "dismissed": False,
    }


def _minimal_order(
    sender: str = "Ahmed",
    item: str = "cheeni",
    amount: float = 500.0,
) -> dict:
    return {
        "date": "2026-11-03",
        "sender": sender,
        "item": item,
        "item_raw": item,
        "quantity": 2.0,
        "unit": "kg",
        "amount_pkr": amount,
        "payment_status": "udhaar",
        "source_line": 6,
        "confidence": "high",
    }


# ---------------------------------------------------------------------------
# 1. GET /api/agent/status — deterministic mode
# ---------------------------------------------------------------------------

class TestAgentStatus:

    def test_status_returns_200(self):
        resp = client.get("/api/agent/status")
        assert resp.status_code == 200

    def test_status_mode_is_deterministic_when_no_key(self):
        resp = client.get("/api/agent/status")
        data = resp.json()
        assert data["mode"] == "deterministic"

    def test_status_no_provider_in_deterministic(self):
        resp = client.get("/api/agent/status")
        data = resp.json()
        # Should not include a provider key (or it is None/absent)
        assert data.get("provider") is None or "provider" not in data

    def test_status_has_label(self):
        resp = client.get("/api/agent/status")
        data = resp.json()
        assert "label" in data
        assert data["label"]  # non-empty

    def test_status_label_mentions_deterministic(self):
        resp = client.get("/api/agent/status")
        label = resp.json()["label"].lower()
        assert "deterministic" in label

    def test_status_no_key_in_response(self):
        """The response must not contain any string that looks like an API key."""
        resp = client.get("/api/agent/status")
        text = resp.text
        # API keys are typically long strings with underscores or dashes
        # We just assert there's no GEMINI or GROQ key placeholder in response
        assert "GEMINI_API_KEY" not in text
        assert "GROQ_API_KEY" not in text


# ---------------------------------------------------------------------------
# 2. POST /api/agent/explain — deterministic mode
# ---------------------------------------------------------------------------

class TestAgentExplain:

    def test_explain_returns_200(self):
        resp = client.post("/api/agent/explain", json={"flag": _minimal_flag()})
        assert resp.status_code == 200

    def test_explain_source_is_template(self):
        resp = client.post("/api/agent/explain", json={"flag": _minimal_flag()})
        data = resp.json()
        assert data["source"] == "template"

    def test_explain_has_explanation(self):
        resp = client.post("/api/agent/explain", json={"flag": _minimal_flag()})
        data = resp.json()
        assert "explanation" in data
        assert isinstance(data["explanation"], str)
        assert data["explanation"].strip()

    def test_explain_cites_evidence(self):
        """Explanation should mention the chat line or ledger row."""
        flag = _minimal_flag(source_line=6, row_index=1)
        resp = client.post("/api/agent/explain", json={"flag": flag})
        explanation = resp.json()["explanation"].lower()
        # Must cite the source (chat line 6 or ledger row 1)
        has_evidence = (
            "6" in explanation
            or "chat" in explanation
            or "ledger" in explanation
            or "row" in explanation
        )
        assert has_evidence, f"Explanation should cite evidence: {explanation!r}"

    def test_explain_paid_not_recorded(self):
        flag = _minimal_flag(kind="PAID_NOT_RECORDED", sender="Usman", item="anda", amount=600.0)
        resp = client.post("/api/agent/explain", json={"flag": flag})
        data = resp.json()
        assert data["source"] == "template"
        explanation = data["explanation"].lower()
        # Should mention payment / paid
        assert "de diya" in explanation or "paid" in explanation or "600" in explanation

    def test_explain_price_mismatch(self):
        flag = _minimal_flag(kind="PRICE_MISMATCH", amount=500.0)
        flag["ledger_rows"][0]["amount_pkr"] = 550.0
        resp = client.post("/api/agent/explain", json={"flag": flag})
        data = resp.json()
        assert data["source"] == "template"
        explanation = data["explanation"]
        # Should mention both amounts
        assert "500" in explanation or "550" in explanation

    def test_explain_duplicate(self):
        flag = _minimal_flag(kind="DUPLICATE")
        flag["chat_order"] = None
        flag["ledger_rows"] = [
            {"row_index": 3, "customer": "Bilal", "item": "atta", "amount_pkr": 450.0, "paid": False},
            {"row_index": 4, "customer": "Bilal", "item": "atta", "amount_pkr": 450.0, "paid": False},
        ]
        resp = client.post("/api/agent/explain", json={"flag": flag})
        data = resp.json()
        assert data["source"] == "template"
        explanation = data["explanation"].lower()
        assert "duplicate" in explanation or "3" in explanation or "4" in explanation

    def test_explain_no_key_in_response(self):
        resp = client.post("/api/agent/explain", json={"flag": _minimal_flag()})
        text = resp.text
        assert "GEMINI_API_KEY" not in text
        assert "GROQ_API_KEY" not in text


# ---------------------------------------------------------------------------
# 3. POST /api/agent/draft-reply — deterministic mode
# ---------------------------------------------------------------------------

class TestAgentDraftReply:

    def test_draft_reply_returns_200(self):
        resp = client.post("/api/agent/draft-reply", json={"order": _minimal_order()})
        assert resp.status_code == 200

    def test_draft_reply_source_is_template(self):
        resp = client.post("/api/agent/draft-reply", json={"order": _minimal_order()})
        data = resp.json()
        assert data["source"] == "template"

    def test_draft_reply_has_draft(self):
        resp = client.post("/api/agent/draft-reply", json={"order": _minimal_order()})
        data = resp.json()
        assert "draft" in data
        assert isinstance(data["draft"], str)
        assert data["draft"].strip()

    def test_draft_reply_contains_customer_name(self):
        """Draft should address the customer by name."""
        order = _minimal_order(sender="Ahmed")
        resp = client.post("/api/agent/draft-reply", json={"order": order})
        draft = resp.json()["draft"]
        assert "Ahmed" in draft or "ahmed" in draft.lower()

    def test_draft_reply_contains_amount(self):
        """Draft should mention the amount."""
        order = _minimal_order(amount=500.0)
        resp = client.post("/api/agent/draft-reply", json={"order": order})
        draft = resp.json()["draft"]
        assert "500" in draft

    def test_draft_reply_contains_item(self):
        """Draft should mention the item."""
        order = _minimal_order(item="cheeni")
        resp = client.post("/api/agent/draft-reply", json={"order": order})
        draft = resp.json()["draft"]
        assert "cheeni" in draft

    def test_draft_reply_roman_urdu_mix(self):
        """Draft should contain at least one Roman Urdu word."""
        order = _minimal_order()
        resp = client.post("/api/agent/draft-reply", json={"order": order})
        draft = resp.json()["draft"].lower()
        roman_urdu_words = {"salam", "bhai", "ka", "rs", "rehta", "hai", "de", "dena",
                            "baaki", "udhaar", "shukriya", "mehrbani"}
        found = any(w in draft for w in roman_urdu_words)
        assert found, f"Draft should contain Roman Urdu words: {draft!r}"

    def test_draft_reply_no_key_in_response(self):
        resp = client.post("/api/agent/draft-reply", json={"order": _minimal_order()})
        text = resp.text
        assert "GEMINI_API_KEY" not in text
        assert "GROQ_API_KEY" not in text

    def test_draft_reply_missing_amount(self):
        """Draft with no amount should still succeed (no crash)."""
        order = _minimal_order()
        order["amount_pkr"] = None
        resp = client.post("/api/agent/draft-reply", json={"order": order})
        assert resp.status_code == 200
        data = resp.json()
        assert data["draft"].strip()

    def test_draft_reply_missing_sender(self):
        """Draft with no sender should still succeed."""
        order = _minimal_order()
        order["sender"] = None
        resp = client.post("/api/agent/draft-reply", json={"order": order})
        assert resp.status_code == 200
        assert resp.json()["draft"].strip()


# ---------------------------------------------------------------------------
# 4. POST /api/agent/structure — deterministic mode
# ---------------------------------------------------------------------------

class TestAgentStructure:

    def test_structure_returns_200(self):
        resp = client.post(
            "/api/agent/structure",
            json={"candidate_orders": [_minimal_order()]},
        )
        assert resp.status_code == 200

    def test_structure_source_is_deterministic(self):
        resp = client.post(
            "/api/agent/structure",
            json={"candidate_orders": [_minimal_order()]},
        )
        data = resp.json()
        assert data["source"] == "deterministic"

    def test_structure_returns_orders_unchanged(self):
        """In deterministic mode, the orders are returned as-is."""
        orders = [_minimal_order("Ahmed", "cheeni", 500.0),
                  _minimal_order("Bilal", "atta", 450.0)]
        resp = client.post("/api/agent/structure", json={"candidate_orders": orders})
        data = resp.json()
        assert "orders" in data
        assert len(data["orders"]) == 2

    def test_structure_empty_list(self):
        """Empty candidate_orders → empty orders returned."""
        resp = client.post("/api/agent/structure", json={"candidate_orders": []})
        data = resp.json()
        assert data["orders"] == []
        assert data["source"] == "deterministic"

    def test_structure_no_key_in_response(self):
        resp = client.post(
            "/api/agent/structure",
            json={"candidate_orders": [_minimal_order()]},
        )
        text = resp.text
        assert "GEMINI_API_KEY" not in text
        assert "GROQ_API_KEY" not in text


# ---------------------------------------------------------------------------
# 5. Invalid-LLM-response fallback
# ---------------------------------------------------------------------------

class TestInvalidLLMFallback:
    """
    Simulate an LLM being configured but returning invalid/bad responses.
    Confirms the agent falls back gracefully to deterministic mode.
    """

    def _patch_llm(self, return_value: str):
        """Context manager that patches _call_llm to return a fixed string."""
        return mock.patch.object(agent_module, "_call_llm", return_value=return_value)

    def _set_fake_key(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")

    def test_invalid_json_falls_back_explain(self, monkeypatch):
        """If LLM returns non-JSON, explain() falls back to template."""
        self._set_fake_key(monkeypatch)
        with self._patch_llm("this is not json at all"):
            result = agent_module.explain(_minimal_flag())
        assert result["source"] == "template"
        assert result["explanation"].strip()

    def test_invalid_json_falls_back_draft(self, monkeypatch):
        """If LLM returns non-JSON, draft_reply() falls back to template."""
        self._set_fake_key(monkeypatch)
        with self._patch_llm("bad response"):
            result = agent_module.draft_reply(_minimal_order())
        assert result["source"] == "template"
        assert result["draft"].strip()

    def test_invalid_json_falls_back_structure(self, monkeypatch):
        """If LLM returns non-JSON, structure() falls back to deterministic."""
        self._set_fake_key(monkeypatch)
        orders = [_minimal_order()]
        with self._patch_llm("not json"):
            result = agent_module.structure(orders)
        assert result["source"] == "deterministic"
        assert result["orders"] == orders

    def test_empty_explanation_falls_back(self, monkeypatch):
        """If LLM returns JSON but explanation is empty, fall back."""
        self._set_fake_key(monkeypatch)
        with self._patch_llm(json.dumps({"explanation": ""})):
            result = agent_module.explain(_minimal_flag())
        assert result["source"] == "template"

    def test_empty_draft_falls_back(self, monkeypatch):
        """If LLM returns JSON but draft is empty, fall back."""
        self._set_fake_key(monkeypatch)
        with self._patch_llm(json.dumps({"draft": "  "})):
            result = agent_module.draft_reply(_minimal_order())
        assert result["source"] == "template"

    def test_missing_orders_key_falls_back(self, monkeypatch):
        """If LLM returns JSON but 'orders' key missing, fall back."""
        self._set_fake_key(monkeypatch)
        orders = [_minimal_order()]
        with self._patch_llm(json.dumps({"result": "something"})):
            result = agent_module.structure(orders)
        assert result["source"] == "deterministic"

    def test_orders_not_a_list_falls_back(self, monkeypatch):
        """If LLM returns 'orders' as a non-list, fall back."""
        self._set_fake_key(monkeypatch)
        orders = [_minimal_order()]
        with self._patch_llm(json.dumps({"orders": "oops a string"})):
            result = agent_module.structure(orders)
        assert result["source"] == "deterministic"

    def test_network_error_falls_back_explain(self, monkeypatch):
        """Network error on LLM call → explain falls back to template."""
        import urllib.error
        self._set_fake_key(monkeypatch)
        with mock.patch.object(
            agent_module, "_call_llm", side_effect=urllib.error.URLError("timeout")
        ):
            result = agent_module.explain(_minimal_flag())
        assert result["source"] == "template"

    def test_network_error_falls_back_draft(self, monkeypatch):
        """Network error on LLM call → draft falls back to template."""
        import urllib.error
        self._set_fake_key(monkeypatch)
        with mock.patch.object(
            agent_module, "_call_llm", side_effect=urllib.error.URLError("timeout")
        ):
            result = agent_module.draft_reply(_minimal_order())
        assert result["source"] == "template"

    def test_agent_note_present_on_fallback(self, monkeypatch):
        """Fallback response includes agent_note explaining the situation."""
        self._set_fake_key(monkeypatch)
        with self._patch_llm("invalid json"):
            result = agent_module.explain(_minimal_flag())
        assert "agent_note" in result
        assert result["agent_note"].strip()


# ---------------------------------------------------------------------------
# 6. Key-safety tests
# ---------------------------------------------------------------------------

class TestKeySafety:
    """
    The API key must never appear in any response or log output.
    """

    FAKE_KEY = "AIza-FAKE-GEMINI-KEY-12345"

    def test_key_not_in_status_response(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", self.FAKE_KEY)
        resp = client.get("/api/agent/status")
        assert self.FAKE_KEY not in resp.text

    def test_key_not_in_explain_response(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", self.FAKE_KEY)
        with mock.patch.object(
            agent_module, "_call_llm",
            return_value=json.dumps({"explanation": "test explanation"})
        ):
            resp = client.post("/api/agent/explain", json={"flag": _minimal_flag()})
        assert self.FAKE_KEY not in resp.text

    def test_key_not_in_draft_response(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", self.FAKE_KEY)
        with mock.patch.object(
            agent_module, "_call_llm",
            return_value=json.dumps({"draft": "test draft"})
        ):
            resp = client.post("/api/agent/draft-reply", json={"order": _minimal_order()})
        assert self.FAKE_KEY not in resp.text

    def test_key_not_in_structure_response(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", self.FAKE_KEY)
        orders = [_minimal_order()]
        with mock.patch.object(
            agent_module, "_call_llm",
            return_value=json.dumps({"orders": orders})
        ):
            resp = client.post(
                "/api/agent/structure", json={"candidate_orders": orders}
            )
        assert self.FAKE_KEY not in resp.text

    def test_key_not_in_logs(self, monkeypatch, caplog):
        """The key value must not appear in any log output."""
        monkeypatch.setenv("GEMINI_API_KEY", self.FAKE_KEY)
        with caplog.at_level(logging.DEBUG, logger="frankenledger.agent"):
            with mock.patch.object(
                agent_module, "_call_llm",
                side_effect=Exception("simulated LLM error")
            ):
                agent_module.explain(_minimal_flag())
        # The fake key must not appear in any log record
        for record in caplog.records:
            assert self.FAKE_KEY not in record.getMessage(), (
                f"Key found in log: {record.getMessage()!r}"
            )


# ---------------------------------------------------------------------------
# 7. draft.explain_flag — all five flag kinds
# ---------------------------------------------------------------------------

class TestExplainFlagTemplates:

    def test_paid_not_recorded(self):
        flag = _minimal_flag(kind="PAID_NOT_RECORDED", sender="Usman", item="anda",
                             amount=600.0, source_line=12)
        text = explain_flag(flag)
        assert isinstance(text, str)
        assert text.strip()
        assert "600" in text or "anda" in text or "Usman" in text

    def test_unmatched_order(self):
        flag = _minimal_flag(kind="UNMATCHED_ORDER", sender="Ahmed", item="cheeni",
                             amount=500.0, source_line=14)
        text = explain_flag(flag)
        assert "Ahmed" in text or "cheeni" in text or "14" in text

    def test_recorded_not_paid(self):
        flag = _minimal_flag(kind="RECORDED_NOT_PAID", sender="Sana", item="doodh",
                             amount=220.0, row_index=2)
        flag["chat_order"] = None
        text = explain_flag(flag)
        assert isinstance(text, str)
        assert text.strip()
        # Should mention the ledger row
        assert "2" in text or "ledger" in text

    def test_price_mismatch(self):
        flag = _minimal_flag(kind="PRICE_MISMATCH", sender="Ahmed", item="cheeni",
                             amount=500.0, source_line=6, row_index=1)
        flag["ledger_rows"][0]["amount_pkr"] = 550.0
        text = explain_flag(flag)
        assert "500" in text or "550" in text

    def test_duplicate(self):
        flag = {
            "flag_id": "dup",
            "kind": "DUPLICATE",
            "chat_order": None,
            "ledger_rows": [
                {"row_index": 3, "customer": "Bilal", "item": "atta",
                 "amount_pkr": 450.0, "paid": False},
                {"row_index": 4, "customer": "Bilal", "item": "atta",
                 "amount_pkr": 450.0, "paid": False},
            ],
            "explanation": "",
            "fix_description": "Keep row 3, remove row 4.",
            "dismissed": False,
        }
        text = explain_flag(flag)
        assert "3" in text or "4" in text or "Bilal" in text

    def test_unknown_kind_uses_fallback(self):
        """Unknown flag kind must not crash; falls back to generic text."""
        flag = _minimal_flag(kind="WEIRD_UNKNOWN_KIND")
        flag["explanation"] = "Some pre-computed explanation."
        text = explain_flag(flag)
        assert isinstance(text, str)
        assert text.strip()

    def test_no_chat_order_does_not_crash(self):
        """Flags with chat_order=None must not crash."""
        flag = _minimal_flag(kind="RECORDED_NOT_PAID")
        flag["chat_order"] = None
        text = explain_flag(flag)
        assert isinstance(text, str)


# ---------------------------------------------------------------------------
# 8. draft.draft_reply — various order shapes
# ---------------------------------------------------------------------------

class TestDraftReplyTemplates:

    def test_basic_draft(self):
        order = _minimal_order("Ahmed", "cheeni", 500.0)
        draft = draft_reply_fn(order)
        assert isinstance(draft, str)
        assert draft.strip()

    def test_contains_customer_name(self):
        order = _minimal_order("Bilal", "atta", 450.0)
        draft = draft_reply_fn(order)
        assert "Bilal" in draft or "bilal" in draft.lower()

    def test_contains_amount(self):
        order = _minimal_order("Sana", "doodh", 220.0)
        draft = draft_reply_fn(order)
        assert "220" in draft

    def test_contains_item(self):
        order = _minimal_order("Fatima", "chawal", 300.0)
        draft = draft_reply_fn(order)
        assert "chawal" in draft

    def test_roman_urdu_greeting(self):
        order = _minimal_order("Ahmed", "cheeni", 500.0)
        draft = draft_reply_fn(order)
        assert "Salam" in draft or "salam" in draft.lower() or "Assalamu" in draft

    def test_handles_none_amount(self):
        order = _minimal_order()
        order["amount_pkr"] = None
        draft = draft_reply_fn(order)
        assert isinstance(draft, str)
        assert draft.strip()

    def test_handles_none_item(self):
        order = _minimal_order()
        order["item"] = None
        order["item_raw"] = None
        draft = draft_reply_fn(order)
        assert isinstance(draft, str)
        assert draft.strip()

    def test_handles_none_sender(self):
        order = _minimal_order()
        order["sender"] = None
        draft = draft_reply_fn(order)
        assert isinstance(draft, str)
        assert draft.strip()

    def test_strips_bhai_from_greeting(self):
        """'Ahmed bhai' in sender → draft addresses 'Ahmed', not 'Ahmed bhai bhai'."""
        order = _minimal_order("Ahmed bhai", "cheeni", 500.0)
        draft = draft_reply_fn(order)
        # Should not double-apply the title
        assert "bhai bhai" not in draft.lower()

    def test_deterministic_same_input_same_output(self):
        """Same order input must always produce the same draft."""
        order = _minimal_order("Ahmed", "cheeni", 500.0)
        draft1 = draft_reply_fn(order)
        draft2 = draft_reply_fn(order)
        assert draft1 == draft2


# ---------------------------------------------------------------------------
# 9. agent.get_mode — reflects env-var state
# ---------------------------------------------------------------------------

class TestGetMode:

    def test_no_key_returns_deterministic(self):
        mode = agent_module.get_mode()
        assert mode["mode"] == "deterministic"
        assert "provider" not in mode or mode.get("provider") is None

    def test_gemini_key_returns_llm_gemini(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")
        mode = agent_module.get_mode()
        assert mode["mode"] == "llm"
        assert mode["provider"] == "gemini"

    def test_groq_key_returns_llm_groq(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "fake-groq-key")
        mode = agent_module.get_mode()
        assert mode["mode"] == "llm"
        assert mode["provider"] == "groq"

    def test_gemini_key_takes_precedence_over_groq(self, monkeypatch):
        """When both keys are set, Gemini is preferred."""
        monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini")
        monkeypatch.setenv("GROQ_API_KEY", "fake-groq")
        mode = agent_module.get_mode()
        assert mode["provider"] == "gemini"

    def test_empty_string_key_treated_as_no_key(self, monkeypatch):
        """An empty string env-var is the same as unset."""
        monkeypatch.setenv("GEMINI_API_KEY", "")
        mode = agent_module.get_mode()
        assert mode["mode"] == "deterministic"


# ---------------------------------------------------------------------------
# 10. Integration: full session demo flow in deterministic mode
# ---------------------------------------------------------------------------

class TestDemoFlowDeterministic:
    """
    Smoke test: upload sample → parse → reconcile → explain a flag →
    draft a reply → structure orders.  All in deterministic mode.
    No LLM key needed.
    """

    def test_full_demo_flow(self):
        # 1. Upload sample
        resp = client.post("/api/upload/sample")
        assert resp.status_code == 200, f"upload/sample failed: {resp.text}"

        # 2. Parse
        resp = client.post("/api/parse")
        assert resp.status_code == 200
        parse_data = resp.json()
        assert parse_data["mode"] == "deterministic"
        candidate_orders = parse_data["orders"]
        assert len(candidate_orders) > 0

        # 3. Reconcile (session-driven)
        resp = client.post("/api/reconcile", json={})
        assert resp.status_code == 200
        rec_data = resp.json()
        assert len(rec_data["flags"]) == 10

        # 4. Agent status — must be deterministic
        resp = client.get("/api/agent/status")
        assert resp.status_code == 200
        assert resp.json()["mode"] == "deterministic"

        # 5. Explain a flag
        flag = rec_data["flags"][0]
        resp = client.post("/api/agent/explain", json={"flag": flag})
        assert resp.status_code == 200
        explain_data = resp.json()
        assert explain_data["source"] == "template"
        assert explain_data["explanation"].strip()

        # 6. Draft a reply for the first chat order
        order = candidate_orders[0]
        resp = client.post("/api/agent/draft-reply", json={"order": order})
        assert resp.status_code == 200
        draft_data = resp.json()
        assert draft_data["source"] == "template"
        assert draft_data["draft"].strip()

        # 7. Structure candidate orders
        resp = client.post(
            "/api/agent/structure",
            json={"candidate_orders": candidate_orders},
        )
        assert resp.status_code == 200
        struct_data = resp.json()
        assert struct_data["source"] == "deterministic"
        assert len(struct_data["orders"]) == len(candidate_orders)
