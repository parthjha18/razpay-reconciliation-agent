#!/usr/bin/env python3
"""CLI: run the full Layer 1-4 pipeline against data/ and print a summary."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reconciliation.pipeline import run_full_pipeline  # noqa: E402
from reconciliation import constants as c  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def main():
    audit = run_full_pipeline(DATA_DIR)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, "audit_trail_full.csv")
    audit.to_csv(out_path, index=False)

    total = len(audit)
    matched = audit["category"].isin(c.MATCHED_CATEGORIES).sum()

    print(f"Audit trail: {total} records -> {out_path}\n")
    print(f"Match rate (Layers 1-3): {matched}/{total} ({matched / total:.1%})\n")
    print("Category breakdown:")
    for category, count in audit["category"].value_counts().items():
        print(f"  {category}: {count}")

    print("\nException list (excluding clean matches):")
    exceptions = audit[~audit["category"].isin(c.MATCHED_CATEGORIES)]
    for _, row in exceptions.iterrows():
        key = row["payment_id"] or row["utr"] or row["invoice_id"]
        print(f"\n[{row['category']}] {key} (Layer {int(row['layer'])}, "
              f"confidence {row['confidence']:.2f})" if pd.notna(row["confidence"])
              else f"\n[{row['category']}] {key} (Layer {int(row['layer'])})")
        print(f"  {row['reason']}")


if __name__ == "__main__":
    main()
