#!/usr/bin/env python3
"""Benchmark the Layer 1-2 matching engine at increasing dataset sizes.

Generates synthetic data in-memory (no CSV I/O), times the matching engine,
and prints throughput + the business-impact equivalent (analyst-hours saved).

Usage:
    python scripts/benchmark_layer1_2.py
"""
import os
import random
import sys
import time
from datetime import datetime, timedelta

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from reconciliation import engine

SIZES = [100, 1_000, 10_000, 100_000]

# Conservative industry estimate: a finance-ops analyst reconciling a payment
# record manually (cross-referencing 3 systems, logging the outcome) takes
# about 3 minutes per record on average. Source: standard assumption used in
# finance-ops automation ROI models; adjust down if you have a faster estimate.
MANUAL_MINUTES_PER_RECORD = 3

BASE_DATE = datetime(2026, 8, 1)
DATASET_AS_OF = datetime(2026, 8, 22)


def _rand_id(prefix: str, rng: random.Random) -> str:
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return prefix + "_" + "".join(rng.choices(chars, k=14))


def make_sources(n: int, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Generate n clean-match transaction triples entirely in memory."""
    rng = random.Random(seed)
    gw_rows, st_rows, ld_rows = [], [], []

    for i in range(n):
        order_id = _rand_id("ord", rng)
        payment_id = _rand_id("pay", rng)
        amount = round(rng.uniform(100, 50_000), 2)
        fee = round(amount * 0.02, 2)
        tax = round(fee * 0.18, 2)
        captured_at = BASE_DATE + timedelta(days=rng.randint(0, 20))
        settlement_date = captured_at + timedelta(days=rng.randint(1, 2))
        utr = str(1_000_000_000 + i)
        invoice_id = _rand_id("inv", rng)

        gw_rows.append({
            "order_id": order_id, "payment_id": payment_id,
            "amount": amount, "currency": "INR", "status": "captured",
            "captured_at": captured_at.strftime("%Y-%m-%d"),
            "gateway_fee": fee, "tax": tax,
        })
        st_rows.append({
            "utr": utr,
            "settlement_amount": round(amount - fee - tax, 2),
            "settlement_date": settlement_date.strftime("%Y-%m-%d"),
            "batch_id": f"BATCH_{rng.randint(1, 50):03d}",
            "payment_id_ref": payment_id,
        })
        ld_rows.append({
            "invoice_id": invoice_id,
            "recorded_amount": amount,
            "recorded_date": captured_at.strftime("%Y-%m-%d"),
            "reference_id": payment_id,
        })

    gateway = pd.DataFrame(gw_rows)
    settlement = pd.DataFrame(st_rows)
    ledger = pd.DataFrame(ld_rows)

    gateway["captured_at"] = pd.to_datetime(gateway["captured_at"])
    settlement["settlement_date"] = pd.to_datetime(settlement["settlement_date"])
    ledger["recorded_date"] = pd.to_datetime(ledger["recorded_date"])
    settlement["utr"] = settlement["utr"].astype(str)

    for col in ("amount", "gateway_fee", "tax"):
        gateway[col] = pd.to_numeric(gateway[col])
    settlement["settlement_amount"] = pd.to_numeric(settlement["settlement_amount"])
    ledger["recorded_amount"] = pd.to_numeric(ledger["recorded_amount"])

    return gateway, settlement, ledger


def fmt_duration(seconds: float) -> str:
    if seconds < 0.001:
        return f"{seconds * 1_000_000:.0f} µs"
    if seconds < 1:
        return f"{seconds * 1000:.1f} ms"
    return f"{seconds:.2f} s"


def main():
    print("Layer 1-2 matching engine benchmark")
    print("=" * 64)
    print(f"{'Records':>10}  {'Total time':>12}  {'Per record':>12}  {'Analyst-hours saved':>20}")
    print("-" * 64)

    results = []
    for n in SIZES:
        gateway, settlement, ledger = make_sources(n)

        runs = 3
        times = []
        for _ in range(runs):
            t0 = time.perf_counter()
            engine.run_layer_1_2(gateway, settlement, ledger)
            times.append(time.perf_counter() - t0)

        best = min(times)
        per_record_ms = best / n * 1000
        analyst_hours = (n * MANUAL_MINUTES_PER_RECORD) / 60

        print(
            f"{n:>10,}  {fmt_duration(best):>12}  {per_record_ms:>9.3f} ms  "
            f"{analyst_hours:>14.0f} h saved"
        )
        results.append((n, best, per_record_ms, analyst_hours))

    print("=" * 64)
    print()

    # Pick the 100k row as the headline number for the pitch
    _, best_100k, per_rec_100k, hours_100k = results[-1]
    print("Key numbers for the pitch:")
    print(f"  • At 100,000 records: full Layer 1-2 run in {fmt_duration(best_100k)}")
    print(f"  • {per_rec_100k:.3f} ms per record (deterministic, no API calls)")
    print(f"  • That same volume manually: ~{hours_100k:.0f} analyst-hours")
    print(f"    ({hours_100k / 8:.0f} working days, {hours_100k / (8 * 22):.1f} analyst-months)")
    print()
    print(f"  Business framing:")
    print(f"  A mid-market merchant processing 5,000 transactions/month")
    n_merchant = 5_000
    # scale from 100k result
    t_merchant = results[-1][1] / 100_000 * n_merchant
    h_merchant = (n_merchant * MANUAL_MINUTES_PER_RECORD) / 60
    print(f"  → Layer 1-2 clears the bulk in {fmt_duration(t_merchant)}")
    print(f"  → vs. ~{h_merchant:.0f} analyst-hours/month of manual work")
    print(f"  → compressed to a few minutes of exception review")


if __name__ == "__main__":
    main()
