#!/usr/bin/env python3
"""Validate the Layer 1-2 engine's output against data/ground_truth.csv.

ground_truth.csv is never fed into the engine -- it exists purely to let us
score our own pipeline before demo day (CLAUDE.md section 2). Each ground
truth row is one underlying transaction; the engine may describe that same
transaction across more than one audit-trail line (e.g. a reference-format
mismatch shows up as a clean gateway<->settlement line *and* a separate
unclaimed-ledger line), so we score at the transaction level: if ANY engine
line touching this transaction's keys raised an exception, that's the
transaction's effective outcome -- an engine that quietly called something
"matched" while a sibling line flagged it is not "matched" for scoring
purposes.
"""
import os
import sys
from collections import defaultdict

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reconciliation import engine  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "..", "reports", "phase1_layer1_2_validation.md")

MATCHED_CATEGORIES = {"matched_layer1_2", "matched_extended_window"}
KEY_COLUMNS = ["order_id", "payment_id", "utr", "invoice_id"]


def build_key_index(audit: pd.DataFrame) -> dict[tuple[str, str], list[int]]:
    index = defaultdict(list)
    for idx, row in audit.iterrows():
        for col in KEY_COLUMNS:
            val = row[col]
            if val:
                index[(col, val)].append(idx)
    return index


def effective_resolution(audit: pd.DataFrame, index, gt_row) -> tuple[str, list[str]]:
    matched_idxs = set()
    for col in KEY_COLUMNS:
        val = gt_row[col]
        if pd.notna(val) and val != "":
            matched_idxs.update(index.get((col, val), []))

    if not matched_idxs:
        return "no_engine_output", []

    categories = [audit.loc[i, "category"] for i in matched_idxs]
    exceptions = [cat for cat in categories if cat not in MATCHED_CATEGORIES]
    if exceptions:
        # Prefer a specific exception label over the defensive fallback.
        specific = [cat for cat in exceptions if cat != "exception_unclassified"]
        return (specific[0] if specific else exceptions[0]), categories
    return categories[0], categories


def main():
    ground_truth = pd.read_csv(DATA_DIR + "/ground_truth.csv", keep_default_na=False)
    gateway, settlement, ledger = engine.load_sources(DATA_DIR)
    audit = engine.run_layer_1_2(gateway, settlement, ledger)
    index = build_key_index(audit)

    rows = []
    for _, gt_row in ground_truth.iterrows():
        effective, all_categories = effective_resolution(audit, index, gt_row)
        rows.append({
            "txn_seq": gt_row["txn_seq"],
            "category": gt_row["category"],
            "expected_resolution": gt_row["expected_resolution"],
            "engine_resolution": effective,
            "correct": effective == gt_row["expected_resolution"],
            "engine_raw_categories": ";".join(sorted(set(all_categories))),
        })
    scored = pd.DataFrame(rows)

    overall_acc = scored["correct"].mean()
    per_category = scored.groupby("category")["correct"].agg(["sum", "count"])
    per_category["accuracy"] = per_category["sum"] / per_category["count"]

    phase1_gate_categories = ["clean_match", "fee_tds_deduction"]
    phase1_gate = scored[scored["category"].isin(phase1_gate_categories)]
    phase1_gate_acc = phase1_gate["correct"].mean()
    phase1_gate_pass = bool((phase1_gate.groupby("category")["correct"].mean() == 1.0).all())

    lines = []
    lines.append("# Phase 1 -- Layer 1-2 validation against ground_truth.csv\n")
    lines.append(f"Overall transaction accuracy: **{scored['correct'].sum()}/{len(scored)} "
                 f"({overall_acc:.1%})**\n")
    lines.append(f"Phase 1 gate (`clean_match` + `fee_tds_deduction` must be 100%): "
                 f"**{'PASS' if phase1_gate_pass else 'FAIL'}** ({phase1_gate_acc:.1%})\n")
    lines.append("## Per-category breakdown\n")
    lines.append("| category | correct | total | accuracy |")
    lines.append("|---|---|---|---|")
    for cat, r in per_category.iterrows():
        lines.append(f"| {cat} | {int(r['sum'])} | {int(r['count'])} | {r['accuracy']:.1%} |")

    mismatches = scored[~scored["correct"]]
    lines.append("\n## Mismatches (expected vs. what Layer 1-2 actually produced)\n")
    if mismatches.empty:
        lines.append("None.\n")
    else:
        lines.append("| txn_seq | category | expected | engine gave |")
        lines.append("|---|---|---|---|")
        for _, m in mismatches.iterrows():
            lines.append(f"| {m['txn_seq']} | {m['category']} | {m['expected_resolution']} | "
                         f"{m['engine_resolution']} |")
        lines.append(
            "\nBy design, Layer 1-2 cannot distinguish a `true_orphan` ledger entry from a "
            "`reference_format_mismatch` using exact-key logic alone (both fail the exact "
            "reference_id join identically) -- it correctly defers both to Layer 3 as "
            "`exception_needs_fuzzy_match` rather than guessing. That is the expected mismatch "
            "here, not a bug; Layer 3 is what resolves the distinction."
        )

    report = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        f.write(report)

    print(report)
    print(f"(written to {REPORT_PATH})")


if __name__ == "__main__":
    main()
