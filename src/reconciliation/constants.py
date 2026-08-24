"""Tolerance bands and category/resolution labels shared by Layers 1-2.

Tolerance values are derived from the data model in CLAUDE.md section 2,
not tuned to this specific seed: the standard settlement window is T+2 days,
currency rounding is a paise-level (single-cent) artifact, and TDS/refund
deductions are always well above a rounding difference.
"""

# A settlement landing within this many days of capture is "on time".
# Anything later is still a deterministic match, just flagged as timing risk.
NORMAL_SETTLEMENT_WINDOW_DAYS = 4

# Amount differences at or below this are float/paise rounding noise, not a
# real mismatch (currency_rounding plants diffs of Rs. 0.01-0.03).
ROUNDING_TOLERANCE = 0.05

# A gateway payment captured within this many days of the dataset's as-of
# date may genuinely not have settled yet -- pending, not lost.
PENDING_SETTLEMENT_WINDOW_DAYS = 3

# --- Resolution labels (mirror ground_truth.csv's expected_resolution vocab
# where Layer 1-2 can fully resolve a category; distinct labels where it
# honestly cannot and must defer to Layer 3/4). ---
MATCHED_LAYER1_2 = "matched_layer1_2"
MATCHED_EXTENDED_WINDOW = "matched_extended_window"
MATCHED_LAYER3 = "matched_layer3"
EXCEPTION_FEE_MISMATCH = "exception_fee_mismatch"
EXCEPTION_REFUND_MISMATCH = "exception_refund_mismatch"
EXCEPTION_DUPLICATE = "exception_duplicate"
EXCEPTION_PENDING_SETTLEMENT = "exception_pending_settlement"
EXCEPTION_ROUNDING = "exception_rounding"
TRUE_EXCEPTION_ORPHAN = "true_exception_orphan"
EXCEPTION_NEEDS_FUZZY_MATCH = "exception_needs_fuzzy_match"  # Layer 3 candidate
EXCEPTION_UNCLASSIFIED = "exception_unclassified"  # defensive fallback
EXCEPTION_MANUAL_REVIEW = "exception_manual_review"  # malformed input or Layer 4 couldn't resolve

MATCHED_CATEGORIES = {MATCHED_LAYER1_2, MATCHED_EXTENDED_WINDOW, MATCHED_LAYER3}

# Categories Layer 1-3 already explained deterministically well enough that
# spending an LLM call on them would be AI-for-everything, not AI-for-judgment.
LAYER4_ELIGIBLE_CATEGORIES = {
    EXCEPTION_FEE_MISMATCH,
    EXCEPTION_REFUND_MISMATCH,
    TRUE_EXCEPTION_ORPHAN,
    EXCEPTION_NEEDS_FUZZY_MATCH,
    EXCEPTION_UNCLASSIFIED,
}
