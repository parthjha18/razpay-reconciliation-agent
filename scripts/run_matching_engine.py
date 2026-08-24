#!/usr/bin/env python3
"""CLI: run the Layer 1-2 matching engine against data/ and print a summary."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reconciliation import engine  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def main():
    gateway, settlement, ledger = engine.load_sources(DATA_DIR)
    audit = engine.run_layer_1_2(gateway, settlement, ledger)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, "audit_trail_l1_l2.csv")
    audit.to_csv(out_path, index=False)

    total = len(audit)
    matched = audit["category"].isin(["matched_layer1_2", "matched_extended_window"]).sum()

    print(f"Sources: {len(gateway)} gateway rows, {len(settlement)} settlement rows, "
          f"{len(ledger)} ledger rows")
    print(f"Audit trail: {total} records -> {out_path}\n")
    print(f"Match rate (Layer 1-2 only): {matched}/{total} ({matched / total:.1%})\n")
    print("Category breakdown:")
    for category, count in audit["category"].value_counts().items():
        print(f"  {category}: {count}")


if __name__ == "__main__":
    main()
