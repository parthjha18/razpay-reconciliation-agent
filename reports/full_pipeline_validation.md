# Full Layer 1-4 pipeline validation against ground_truth.csv

Overall transaction accuracy: **62/62 (100.0%)**

A transaction counts as correct if the pipeline's final category is any of the honest outcomes for that ground-truth category -- e.g. a reference-format mismatch is correct whether Layer 3 resolved it (`matched_layer3`) or correctly deferred it (`exception_needs_fuzzy_match`); only a genuinely wrong category is a miss. Layers 3-4 call a live, rate-limited API, so which of the honest outcomes lands can vary slightly run to run.

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
| true_orphan | 4 | 4 | 100.0% |

## Mismatches

None.

