"""Layer 3 correctness with a mocked LLM (no live API key required)."""
import pandas as pd

from reconciliation import constants as c
from reconciliation import engine
from reconciliation.layer3_fuzzy_match import run_layer_3


def _reference_format_mismatch_sources():
    gateway = pd.DataFrame([{
        "order_id": "order_1", "payment_id": "pay_ABC123", "amount": 2000.0, "currency": "INR",
        "status": "captured", "captured_at": pd.Timestamp("2026-08-10"), "gateway_fee": 40.0, "tax": 0.0,
    }])
    settlement = pd.DataFrame([{
        "utr": "9999", "settlement_amount": 1960.0, "settlement_date": pd.Timestamp("2026-08-12"),
        "batch_id": "BATCH-1", "payment_id_ref": "pay_ABC123",
    }])
    ledger = pd.DataFrame([{
        "invoice_id": "INV-1", "recorded_amount": 2000.0, "recorded_date": pd.Timestamp("2026-08-10"),
        "reference_id": "abc123",  # lowercased, prefix dropped -- same transaction
    }])
    return gateway, settlement, ledger


def test_high_confidence_match_merges_the_two_sibling_rows_into_one(monkeypatch):
    gateway, settlement, ledger = _reference_format_mismatch_sources()
    audit = engine.run_layer_1_2(gateway, settlement, ledger)
    assert (audit["category"] == c.EXCEPTION_NEEDS_FUZZY_MATCH).sum() == 2

    monkeypatch.setattr(
        "reconciliation.layer3_fuzzy_match.call_tool",
        lambda **kwargs: {"is_match": True, "confidence": 0.95, "reason": "Same alphanumerics, just re-cased."},
    )

    result = run_layer_3(audit, gateway, ledger)

    matched = result[result["category"] == c.MATCHED_LAYER3]
    assert len(matched) == 1, "the two sibling exception rows should collapse into one resolved row"
    row = matched.iloc[0]
    assert row["payment_id"] == "pay_ABC123"
    assert row["invoice_id"] == "INV-1"
    assert row["confidence"] == 0.95
    assert (result["category"] == c.EXCEPTION_NEEDS_FUZZY_MATCH).sum() == 0


def test_low_confidence_match_is_left_for_layer4_not_forced(monkeypatch):
    gateway, settlement, ledger = _reference_format_mismatch_sources()
    audit = engine.run_layer_1_2(gateway, settlement, ledger)

    monkeypatch.setattr(
        "reconciliation.layer3_fuzzy_match.call_tool",
        lambda **kwargs: {"is_match": True, "confidence": 0.4, "reason": "Plausible but not certain."},
    )

    result = run_layer_3(audit, gateway, ledger)

    assert (result["category"] == c.MATCHED_LAYER3).sum() == 0
    still_pending = result[result["category"] == c.EXCEPTION_NEEDS_FUZZY_MATCH]
    assert len(still_pending) == 2
    assert all("below" in reason for reason in still_pending["reason"])


def test_no_amount_candidate_skips_the_llm_call_entirely(monkeypatch):
    gateway, settlement, ledger = _reference_format_mismatch_sources()
    # A true orphan ledger row: no gateway payment anywhere near this amount.
    ledger.loc[len(ledger)] = {
        "invoice_id": "INV-2", "recorded_amount": 999999.0,
        "recorded_date": pd.Timestamp("2026-08-10"), "reference_id": "pay_totally_unrelated",
    }
    audit = engine.run_layer_1_2(gateway, settlement, ledger)

    calls = []
    monkeypatch.setattr(
        "reconciliation.layer3_fuzzy_match.call_tool",
        lambda **kwargs: calls.append(kwargs) or {"is_match": True, "confidence": 0.99, "reason": "x"},
    )

    result = run_layer_3(audit, gateway, ledger)

    orphan_row = result[result["invoice_id"] == "INV-2"].iloc[0]
    assert orphan_row["category"] == c.EXCEPTION_NEEDS_FUZZY_MATCH
    assert "no gateway candidate within amount tolerance" in orphan_row["reason"]
    # Only the one real ambiguous pair (INV-1) should have triggered an LLM call.
    assert len(calls) == 1
