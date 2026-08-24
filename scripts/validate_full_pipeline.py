#!/usr/bin/env python3
"""Validate the full Layer 1-4 pipeline's output against data/ground_truth.csv.

Unlike scripts/validate_against_ground_truth.py (which checks Layer 1-2 alone
against the *exact* expected_resolution label), this scores full-pipeline
correctness: some categories have two honest correct outcomes depending on
whether a Layer 3/4 model call actually landed this run (the free tier can
be flaky) or correctly deferred instead of guessing. A reference-format
mismatch that Layer 3 resolves into a real match (matched_layer3) is just as
correct as one still honestly flagged exception_needs_fuzzy_match -- both are
right; only a genuinely wrong category is a miss.
"""
import os
import sys
from collections import defaultdict

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")
AUDIT_PATH = os.path.join(OUTPUT_DIR, "audit_trail_full.csv")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "..", "reports", "full_pipeline_validation.md")

KEY_COLUMNS = ["order_id", "payment_id", "utr", "invoice_id"]
MATCHED_CATEGORIES = {"matched_layer1_2", "matched_extended_window", "matched_layer3"}

ACCEPTABLE_OUTCOMES = {
    "clean_match": {"matched_layer1_2"},
    "timing_difference": {"matched_extended_window"},
    "fee_tds_deduction": {"exception_fee_mismatch"},
    "duplicate_entry": {"exception_duplicate"},
    "missing_settlement": {"exception_pending_settlement"},
    "partial_refund_mismatch": {"exception_refund_mismatch"},
    "reference_format_mismatch": {"exception_needs_fuzzy_match", "matched_layer3"},
    "currency_rounding": {"exception_rounding"},
    "true_orphan": {"true_exception_orphan", "exception_needs_fuzzy_match"},
}


def build_key_index(audit: pd.DataFrame) -> dict:
    index = defaultdict(list)
    for idx, row in audit.iterrows():
        for col in KEY_COLUMNS:
            val = row[col]
            if val:
                index[(col, val)].append(idx)
    return index


def effective_resolution(audit: pd.DataFrame, index, gt_row) -> str:
    matched_idxs = set()
    for col in KEY_COLUMNS:
        val = gt_row[col]
        if val:
            matched_idxs.update(index.get((col, val), []))
    if not matched_idxs:
        return "no_engine_output"
    categories = [audit.loc[i, "category"] for i in matched_idxs]
    exceptions = [c for c in categories if c not in MATCHED_CATEGORIES]
    return exceptions[0] if exceptions else categories[0]


def main():
    if not os.path.exists(AUDIT_PATH):
        print(f"No {AUDIT_PATH} found -- run scripts/run_pipeline.py first.")
        sys.exit(1)

    ground_truth = pd.read_csv(DATA_DIR + "/ground_truth.csv", keep_default_na=False)
    audit = pd.read_csv(AUDIT_PATH, keep_default_na=False)
    index = build_key_index(audit)

    rows = []
    for _, gt_row in ground_truth.iterrows():
        effective = effective_resolution(audit, index, gt_row)
        acceptable = ACCEPTABLE_OUTCOMES.get(gt_row["category"], {gt_row["expected_resolution"]})
        rows.append({
            "txn_seq": gt_row["txn_seq"], "category": gt_row["category"],
            "engine_resolution": effective, "correct": effective in acceptable,
        })
    scored = pd.DataFrame(rows)

    overall_acc = scored["correct"].mean()
    per_category = scored.groupby("category")["correct"].agg(["sum", "count"])
    per_category["accuracy"] = per_category["sum"] / per_category["count"]

    lines = ["# Full Layer 1-4 pipeline validation against ground_truth.csv\n"]
    lines.append(f"Overall transaction accuracy: **{scored['correct'].sum()}/{len(scored)} "
                 f"({overall_acc:.1%})**\n")
    lines.append("A transaction counts as correct if the pipeline's final category is any of "
                 "the honest outcomes for that ground-truth category -- e.g. a reference-format "
                 "mismatch is correct whether Layer 3 resolved it (`matched_layer3`) or correctly "
                 "deferred it (`exception_needs_fuzzy_match`); only a genuinely wrong category is "
                 "a miss. Layers 3-4 call a live, rate-limited API, so which of the honest outcomes "
                 "lands can vary slightly run to run.\n")
    lines.append("## Per-category breakdown\n")
    lines.append("| category | correct | total | accuracy |")
    lines.append("|---|---|---|---|")
    for cat, r in per_category.iterrows():
        lines.append(f"| {cat} | {int(r['sum'])} | {int(r['count'])} | {r['accuracy']:.1%} |")

    mismatches = scored[~scored["correct"]]
    lines.append("\n## Mismatches\n")
    if mismatches.empty:
        lines.append("None.\n")
    else:
        lines.append("| txn_seq | category | engine gave |")
        lines.append("|---|---|---|")
        for _, m in mismatches.iterrows():
            lines.append(f"| {m['txn_seq']} | {m['category']} | {m['engine_resolution']} |")

    report = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        f.write(report)

    print(report)
    print(f"(written to {REPORT_PATH})")


if __name__ == "__main__":
    main()
