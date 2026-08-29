"""Unit tests for the deterministic heuristic fuzzy-match fallback."""
import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reconciliation.heuristic_fuzzy import heuristic_match


MATCH_CASES = [
    ("PAY_ABC123",   "pay_abc123"),   # case only
    ("pay_abc123",   "PAY_ABC123"),   # case only (symmetric)
    ("ABC123",       "pay_abc123"),   # missing prefix
    ("pay-abc-123",  "pay_abc_123"),  # separator style
    ("PAY-ABC123",   "pay_abc123"),   # both case + separator
]

NO_MATCH_CASES = [
    ("pay_abc123",   "pay_xyz789"),   # completely different
    ("ref_00001",    "pay_abc123"),   # unrelated references
]


@pytest.mark.parametrize("ref,pid", MATCH_CASES)
def test_normalized_identical_returns_match(ref, pid):
    result = heuristic_match(ref, pid)
    assert result["is_match"] is True
    assert result["confidence"] >= 0.75
    assert "Heuristic" in result["reason"]


@pytest.mark.parametrize("ref,pid", NO_MATCH_CASES)
def test_different_strings_return_no_match(ref, pid):
    result = heuristic_match(ref, pid)
    assert result["is_match"] is False
    assert result["confidence"] < 0.75


def test_confidence_capped_below_threshold_for_near_miss():
    result = heuristic_match("pay_abc1234", "pay_abc1235")
    # Close but different: SequenceMatcher * 0.7 caps them below 0.75
    assert result["confidence"] < 0.75


def test_result_schema_complete():
    result = heuristic_match("REF_001", "pay_ref001")
    assert {"is_match", "confidence", "reason"} <= result.keys()
    assert isinstance(result["is_match"], bool)
    assert 0.0 <= result["confidence"] <= 1.0
    assert isinstance(result["reason"], str)
