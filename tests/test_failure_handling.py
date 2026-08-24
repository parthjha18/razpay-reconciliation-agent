"""CLAUDE.md section 5 -- prove both required failure scenarios degrade
gracefully instead of crashing or guessing."""
import pandas as pd
import pytest

from reconciliation import constants as c
from reconciliation import engine
from reconciliation.ai_client import LLMCallFailed
from reconciliation.layer3_fuzzy_match import run_layer_3
from reconciliation.layer4_classify import run_layer_4


def _minimal_sources():
    gateway = pd.DataFrame([
        {"order_id": "order_1", "payment_id": "pay_1", "amount": 1000.0, "currency": "INR",
         "status": "captured", "captured_at": "2026-08-10T10:00:00", "gateway_fee": 20.0, "tax": 0.0},
        # Malformed: payment_id missing entirely.
        {"order_id": "order_2", "payment_id": "", "amount": 500.0, "currency": "INR",
         "status": "captured", "captured_at": "2026-08-10T11:00:00", "gateway_fee": 10.0, "tax": 0.0},
        # Malformed: amount is not a number.
        {"order_id": "order_3", "payment_id": "pay_3", "amount": "not_a_number", "currency": "INR",
         "status": "captured", "captured_at": "2026-08-10T12:00:00", "gateway_fee": 10.0, "tax": 0.0},
    ])
    settlement = pd.DataFrame([
        {"utr": "1111", "settlement_amount": 980.0, "settlement_date": "2026-08-12",
         "batch_id": "BATCH-1", "payment_id_ref": "pay_1"},
    ])
    ledger = pd.DataFrame([
        {"invoice_id": "INV-1", "recorded_amount": 1000.0, "recorded_date": "2026-08-10",
         "reference_id": "pay_1"},
    ])
    gateway["captured_at"] = pd.to_datetime(gateway["captured_at"], errors="coerce")
    settlement["settlement_date"] = pd.to_datetime(settlement["settlement_date"], errors="coerce")
    ledger["recorded_date"] = pd.to_datetime(ledger["recorded_date"], errors="coerce")
    gateway["amount"] = pd.to_numeric(gateway["amount"], errors="coerce")
    return gateway, settlement, ledger


def test_malformed_gateway_records_are_flagged_not_dropped_or_crashed():
    gateway, settlement, ledger = _minimal_sources()

    audit = engine.run_layer_1_2(gateway, settlement, ledger)  # must not raise

    manual_review = audit[audit["category"] == c.EXCEPTION_MANUAL_REVIEW]
    assert len(manual_review) == 2, "both malformed rows should be flagged, not silently dropped"

    good = audit[audit["payment_id"] == "pay_1"]
    assert len(good) == 1
    assert good.iloc[0]["category"] == c.MATCHED_LAYER1_2, "the one well-formed record still matches normally"


def test_malformed_settlement_and_ledger_rows_are_flagged():
    gateway, settlement, ledger = _minimal_sources()
    settlement.loc[len(settlement)] = {
        "utr": "", "settlement_amount": 50.0, "settlement_date": "2026-08-12",
        "batch_id": "BATCH-2", "payment_id_ref": "",
    }
    ledger.loc[len(ledger)] = {
        "invoice_id": "INV-2", "recorded_amount": None, "recorded_date": "2026-08-12",
        "reference_id": "pay_9",
    }
    settlement["settlement_date"] = pd.to_datetime(settlement["settlement_date"], errors="coerce")
    ledger["recorded_date"] = pd.to_datetime(ledger["recorded_date"], errors="coerce")

    audit = engine.run_layer_1_2(gateway, settlement, ledger)  # must not raise

    manual_review_types = set(audit[audit["category"] == c.EXCEPTION_MANUAL_REVIEW]["record_type"])
    assert "settlement_orphan" in manual_review_types
    assert "ledger_orphan" in manual_review_types


def test_layer3_llm_failure_falls_back_to_layer4_queue_instead_of_crashing(monkeypatch):
    gateway, settlement, ledger = _minimal_sources()
    gateway = pd.concat([gateway.iloc[[0]], pd.DataFrame([{
        "order_id": "order_4", "payment_id": "pay_4", "amount": 2000.0, "currency": "INR",
        "status": "captured", "captured_at": pd.Timestamp("2026-08-10"), "gateway_fee": 40.0, "tax": 0.0,
    }])], ignore_index=True)
    settlement = pd.concat([settlement, pd.DataFrame([{
        "utr": "2222", "settlement_amount": 1960.0, "settlement_date": pd.Timestamp("2026-08-12"),
        "batch_id": "BATCH-3", "payment_id_ref": "pay_4",
    }])], ignore_index=True)
    # Ledger reference is a mangled variant of pay_4 with the same amount -- exactly
    # the shape that should trigger a Layer 3 LLM call.
    ledger = pd.concat([ledger, pd.DataFrame([{
        "invoice_id": "INV-4", "recorded_amount": 2000.0, "recorded_date": pd.Timestamp("2026-08-10"),
        "reference_id": "pay4",
    }])], ignore_index=True)

    audit = engine.run_layer_1_2(gateway, settlement, ledger)
    assert (audit["category"] == c.EXCEPTION_NEEDS_FUZZY_MATCH).sum() == 2

    def _raise_timeout(**kwargs):
        raise LLMCallFailed("APITimeoutError: simulated timeout")

    monkeypatch.setattr("reconciliation.layer3_fuzzy_match.call_tool", _raise_timeout)

    result = run_layer_3(audit, gateway, ledger)  # must not raise, must not hang, must not guess

    still_pending = result[result["category"] == c.EXCEPTION_NEEDS_FUZZY_MATCH]
    assert len(still_pending) == 2, "a failed LLM call must defer to Layer 4, not silently match or drop"
    assert all("Layer 3 LLM call failed" in reason for reason in still_pending["reason"])


def test_layer4_llm_failure_retains_prior_classification_instead_of_crashing(monkeypatch):
    audit = pd.DataFrame([{
        "record_type": "gateway_payment", "order_id": "order_5", "payment_id": "pay_5",
        "utr": "3333", "invoice_id": "", "layer": 2, "category": c.EXCEPTION_FEE_MISMATCH,
        "confidence": 1.0, "reason": "Settlement short by Rs.100, not explained by the fee formula.",
    }])

    def _raise_timeout(**kwargs):
        raise LLMCallFailed("APITimeoutError: simulated timeout")

    monkeypatch.setattr("reconciliation.layer4_classify.call_tool", _raise_timeout)

    result = run_layer_4(audit)  # must not raise

    assert result.iloc[0]["category"] == c.EXCEPTION_FEE_MISMATCH, "must retain the deterministic finding"
    assert "Layer 4 LLM call failed" in result.iloc[0]["reason"]
