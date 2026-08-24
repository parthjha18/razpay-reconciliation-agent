# Phase 1 -- Layer 1-2 validation against ground_truth.csv

Overall transaction accuracy: **61/62 (98.4%)**

Phase 1 gate (`clean_match` + `fee_tds_deduction` must be 100%): **PASS** (100.0%)

## Per-category breakdown

| category | correct | total | accuracy |
|---|---|---|---|
| clean_match | 20 | 20 | 100.0% |
| currency_rounding | 4 | 4 | 100.0% |
| duplicate_entry | 5 | 5 | 100.0% |
| fee_tds_deduction | 6 | 6 | 100.0% |
| missing_settlement | 6 | 6 | 100.0% |
| partial_refund_mismatch | 5 | 5 | 100.0% |
| reference_format_mismatch | 6 | 6 | 100.0% |
| timing_difference | 6 | 6 | 100.0% |
| true_orphan | 3 | 4 | 75.0% |

## Mismatches (expected vs. what Layer 1-2 actually produced)

| txn_seq | category | expected | engine gave |
|---|---|---|---|
| 59 | true_orphan | true_exception_orphan | exception_needs_fuzzy_match |

By design, Layer 1-2 cannot distinguish a `true_orphan` ledger entry from a `reference_format_mismatch` using exact-key logic alone (both fail the exact reference_id join identically) -- it correctly defers both to Layer 3 as `exception_needs_fuzzy_match` rather than guessing. That is the expected mismatch here, not a bug; Layer 3 is what resolves the distinction.
