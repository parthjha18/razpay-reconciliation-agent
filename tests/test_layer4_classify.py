"""Layer 4 correctness with a mocked LLM (no live API key required)."""
import pandas as pd

from reconciliation import constants as c
from reconciliation.layer4_classify import run_layer_4


def _fee_mismatch_row():
    return pd.DataFrame([{
        "record_type": "gateway_payment", "order_id": "order_1", "payment_id": "pay_1",
        "utr": "1111", "invoice_id": "", "layer": 2, "category": c.EXCEPTION_FEE_MISMATCH,
        "confidence": 1.0, "reason": "Settlement short by Rs.100, not explained by the fee formula.",
    }])


def test_confirming_the_prior_category_is_always_accepted(monkeypatch):
    monkeypatch.setattr(
        "reconciliation.layer4_classify.call_tool",
        lambda **kwargs: {"category": "fee_or_tds_deduction", "confidence": 0.55,
                           "explanation": "Consistent with an unreflected TDS deduction."},
    )
    result = run_layer_4(_fee_mismatch_row())
    row = result.iloc[0]
    assert row["category"] == c.EXCEPTION_FEE_MISMATCH
    assert row["layer"] == 4
    assert "unreflected TDS" in row["reason"]


def test_low_confidence_override_is_rejected_keeping_prior_category(monkeypatch):
    monkeypatch.setattr(
        "reconciliation.layer4_classify.call_tool",
        lambda **kwargs: {"category": "true_orphan", "confidence": 0.5,
                           "explanation": "Might be unrelated."},
    )
    result = run_layer_4(_fee_mismatch_row())
    assert result.iloc[0]["category"] == c.EXCEPTION_FEE_MISMATCH, (
        "a below-threshold override must not silently replace the deterministic finding"
    )


def test_high_confidence_override_is_accepted(monkeypatch):
    monkeypatch.setattr(
        "reconciliation.layer4_classify.call_tool",
        lambda **kwargs: {"category": "true_orphan", "confidence": 0.9,
                           "explanation": "No plausible fee formula explains this gap; likely unrelated."},
    )
    result = run_layer_4(_fee_mismatch_row())
    assert result.iloc[0]["category"] == c.TRUE_EXCEPTION_ORPHAN


def test_only_layer4_eligible_categories_are_touched(monkeypatch):
    audit = pd.DataFrame([{
        "record_type": "gateway_payment", "order_id": "order_2", "payment_id": "pay_2",
        "utr": "2222", "invoice_id": "INV-2", "layer": 2, "category": c.EXCEPTION_ROUNDING,
        "confidence": 1.0, "reason": "Rs.0.02 rounding artifact.",
    }])
    calls = []
    monkeypatch.setattr(
        "reconciliation.layer4_classify.call_tool",
        lambda **kwargs: calls.append(kwargs) or {"category": "true_orphan", "confidence": 1.0, "explanation": "x"},
    )
    result = run_layer_4(audit)
    assert len(calls) == 0, "already-well-explained deterministic exceptions should not burn an LLM call"
    assert result.iloc[0]["category"] == c.EXCEPTION_ROUNDING
