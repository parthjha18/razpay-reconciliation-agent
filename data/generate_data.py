"""
Synthetic reconciliation dataset generator for Track 04.

Generates three misaligned data sources (Payment Gateway Log, Bank Settlement
File, Merchant Ledger) that a reconciliation agent must match up, plus a
ground_truth.csv that is NOT meant to be fed into the matching engine -- it's
for you to validate your own pipeline's accuracy before demo day.

Run: python generate_data.py
Re-run with a different seed to get a fresh dataset: python generate_data.py --seed 7
"""

import argparse
import csv
import os
import random
import string
from datetime import datetime, timedelta

OUTPUT_DIR = "output_data"
BASE_DATE = datetime(2026, 8, 1)
DATASET_AS_OF = datetime(2026, 8, 22)  # "today" from the dataset's point of view

# How many base transactions to generate per category.
# Total = 62 base transactions -> comfortably >50 rows per source once
# duplicates/orphans are added, and each source ends up with a slightly
# different row count -- which is the whole point of a reconciliation problem.
CATEGORY_COUNTS = {
    "clean_match": 20,
    "timing_difference": 6,
    "fee_tds_deduction": 6,
    "duplicate_entry": 5,
    "missing_settlement": 6,
    "partial_refund_mismatch": 5,
    "reference_format_mismatch": 6,
    "currency_rounding": 4,
    "true_orphan": 4,
}

GATEWAY_FEE_RATE = 0.02   # 2% gateway fee
GST_ON_FEE_RATE = 0.18    # 18% GST on the fee itself


def random_id(prefix, length=14):
    chars = string.ascii_letters + string.digits
    return prefix + "".join(random.choices(chars, k=length))


def random_utr():
    return "".join(random.choices(string.digits, k=16))


def random_amount(low=500, high=85000):
    return round(random.uniform(low, high), 2)


def random_capture_time(days_back_min=2, days_back_max=20):
    day_offset = random.randint(days_back_min, days_back_max)
    dt = DATASET_AS_OF - timedelta(days=day_offset)
    dt = dt.replace(hour=random.randint(8, 22), minute=random.randint(0, 59), second=random.randint(0, 59))
    return dt


def compute_fee(amount):
    fee = round(amount * GATEWAY_FEE_RATE, 2)
    gst = round(fee * GST_ON_FEE_RATE, 2)
    return round(fee + gst, 2)


def gw_row(order_id, payment_id, amount, status, captured_at, fee, tax=0.0):
    return {
        "order_id": order_id,
        "payment_id": payment_id,
        "amount": amount,
        "currency": "INR",
        "status": status,
        "captured_at": captured_at.isoformat(),
        "gateway_fee": fee,
        "tax": tax,
    }


def settle_row(utr, settlement_amount, settlement_date, batch_id, payment_id_ref):
    return {
        "utr": utr,
        "settlement_amount": settlement_amount,
        "settlement_date": settlement_date.date().isoformat(),
        "batch_id": batch_id,
        "payment_id_ref": payment_id_ref,
    }


def ledger_row(invoice_id, recorded_amount, recorded_date, reference_id):
    return {
        "invoice_id": invoice_id,
        "recorded_amount": recorded_amount,
        "recorded_date": recorded_date.date().isoformat(),
        "reference_id": reference_id,
    }


def batch_id_for(dt):
    return f"BATCH-{dt.strftime('%Y%m%d')}"


def build_dataset(seed):
    random.seed(seed)

    gateway_rows, settlement_rows, ledger_rows, ground_truth_rows = [], [], [], []
    seq = 0

    def next_invoice():
        nonlocal seq
        seq += 1
        return f"INV-2026-{seq:04d}"

    def add_gt(category, order_id, payment_id, utr, invoice_id, resolution, notes):
        ground_truth_rows.append({
            "txn_seq": seq,
            "category": category,
            "order_id": order_id or "",
            "payment_id": payment_id or "",
            "utr": utr or "",
            "invoice_id": invoice_id or "",
            "expected_resolution": resolution,
            "notes": notes,
        })

    # 1. clean_match -- resolves cleanly via exact key join + standard fee formula
    for _ in range(CATEGORY_COUNTS["clean_match"]):
        order_id, payment_id = random_id("order_"), random_id("pay_")
        amount = random_amount()
        captured_at = random_capture_time()
        fee = compute_fee(amount)
        settlement_date = captured_at + timedelta(days=2)
        utr = random_utr()
        invoice_id = next_invoice()

        gateway_rows.append(gw_row(order_id, payment_id, amount, "captured", captured_at, fee))
        settlement_rows.append(settle_row(utr, round(amount - fee, 2), settlement_date, batch_id_for(settlement_date), payment_id))
        ledger_rows.append(ledger_row(invoice_id, amount, captured_at, payment_id))
        add_gt("clean_match", order_id, payment_id, utr, invoice_id, "matched_layer1_2",
               "Standard match: exact keys + fee formula, on-time settlement.")

    # 2. timing_difference -- settlement lands well outside the normal T+2 window
    for _ in range(CATEGORY_COUNTS["timing_difference"]):
        order_id, payment_id = random_id("order_"), random_id("pay_")
        amount = random_amount()
        captured_at = random_capture_time(days_back_min=8, days_back_max=20)
        fee = compute_fee(amount)
        settlement_date = captured_at + timedelta(days=random.randint(6, 10))
        utr = random_utr()
        invoice_id = next_invoice()

        gateway_rows.append(gw_row(order_id, payment_id, amount, "captured", captured_at, fee))
        settlement_rows.append(settle_row(utr, round(amount - fee, 2), settlement_date, batch_id_for(settlement_date), payment_id))
        ledger_rows.append(ledger_row(invoice_id, amount, captured_at, payment_id))
        add_gt("timing_difference", order_id, payment_id, utr, invoice_id, "matched_extended_window",
               f"Settlement landed {(settlement_date - captured_at).days} days after capture -- "
               "true match, but a naive fixed date-window join will miss it.")

    # 3. fee_tds_deduction -- an extra deduction not explained by the standard fee formula
    for _ in range(CATEGORY_COUNTS["fee_tds_deduction"]):
        order_id, payment_id = random_id("order_"), random_id("pay_")
        amount = random_amount(20000, 85000)
        captured_at = random_capture_time()
        fee = compute_fee(amount)
        extra_tds = round(amount * 0.01, 2)  # hidden 1% TDS not reflected in gateway_fee field
        settlement_date = captured_at + timedelta(days=2)
        utr = random_utr()
        invoice_id = next_invoice()

        gateway_rows.append(gw_row(order_id, payment_id, amount, "captured", captured_at, fee))
        settlement_rows.append(settle_row(utr, round(amount - fee - extra_tds, 2), settlement_date, batch_id_for(settlement_date), payment_id))
        ledger_rows.append(ledger_row(invoice_id, amount, captured_at, payment_id))
        add_gt("fee_tds_deduction", order_id, payment_id, utr, invoice_id, "exception_fee_mismatch",
               f"Settlement is short by an extra Rs.{extra_tds} not explained by the standard "
               "fee formula -- likely an unreflected TDS deduction. Needs Layer 3/4 reasoning.")

    # 4. duplicate_entry -- same payment logged twice in the gateway log
    for _ in range(CATEGORY_COUNTS["duplicate_entry"]):
        order_id, payment_id = random_id("order_"), random_id("pay_")
        amount = random_amount()
        captured_at = random_capture_time()
        fee = compute_fee(amount)
        settlement_date = captured_at + timedelta(days=2)
        utr = random_utr()
        invoice_id = next_invoice()

        gateway_rows.append(gw_row(order_id, payment_id, amount, "captured", captured_at, fee))
        gateway_rows.append(gw_row(order_id, payment_id, amount, "captured",
                                    captured_at + timedelta(seconds=random.randint(1, 30)), fee))
        settlement_rows.append(settle_row(utr, round(amount - fee, 2), settlement_date, batch_id_for(settlement_date), payment_id))
        ledger_rows.append(ledger_row(invoice_id, amount, captured_at, payment_id))
        add_gt("duplicate_entry", order_id, payment_id, utr, invoice_id, "exception_duplicate",
               "Same payment logged twice in the gateway source (double webhook). "
               "Only one real settlement/ledger entry exists -- must be deduplicated, not double-counted.")

    # 5. missing_settlement -- captured very recently, settlement genuinely hasn't landed yet
    for _ in range(CATEGORY_COUNTS["missing_settlement"]):
        order_id, payment_id = random_id("order_"), random_id("pay_")
        amount = random_amount()
        captured_at = random_capture_time(days_back_min=0, days_back_max=1)
        fee = compute_fee(amount)
        invoice_id = next_invoice()

        gateway_rows.append(gw_row(order_id, payment_id, amount, "captured", captured_at, fee))
        # No settlement row -- it just hasn't happened yet.
        ledger_rows.append(ledger_row(invoice_id, amount, captured_at, payment_id))  # accrual booking
        add_gt("missing_settlement", order_id, payment_id, None, invoice_id, "exception_pending_settlement",
               "Captured too recently for settlement to have landed as of the dataset's as-of date. "
               "Not a real problem -- should be flagged 'pending', not 'lost'.")

    # 6. partial_refund_mismatch -- ledger still shows the gross amount after a partial refund
    for _ in range(CATEGORY_COUNTS["partial_refund_mismatch"]):
        order_id, payment_id = random_id("order_"), random_id("pay_")
        amount = random_amount(5000, 60000)
        captured_at = random_capture_time()
        refund_fraction = random.choice([0.2, 0.3, 0.5])
        refund_amount = round(amount * refund_fraction, 2)
        net_amount = round(amount - refund_amount, 2)
        fee = compute_fee(net_amount)
        settlement_date = captured_at + timedelta(days=2)
        utr = random_utr()
        invoice_id = next_invoice()

        gateway_rows.append(gw_row(order_id, payment_id, amount, "partially_refunded", captured_at, fee))
        settlement_rows.append(settle_row(utr, round(net_amount - fee, 2), settlement_date, batch_id_for(settlement_date), payment_id))
        ledger_rows.append(ledger_row(invoice_id, amount, captured_at, payment_id))  # ledger not updated for refund
        add_gt("partial_refund_mismatch", order_id, payment_id, utr, invoice_id, "exception_refund_mismatch",
               f"Rs.{refund_amount} partial refund issued after capture. Settlement reflects the net "
               "amount but the ledger still shows the original gross amount.")

    # 7. reference_format_mismatch -- same transaction, cosmetically different reference in the ledger
    for _ in range(CATEGORY_COUNTS["reference_format_mismatch"]):
        order_id, payment_id = random_id("order_"), random_id("pay_")
        amount = random_amount()
        captured_at = random_capture_time()
        fee = compute_fee(amount)
        settlement_date = captured_at + timedelta(days=2)
        utr = random_utr()
        invoice_id = next_invoice()

        mangle = random.choice(["lowercase", "no_prefix", "truncated", "dashes"])
        if mangle == "lowercase":
            ledger_ref = payment_id.lower()
        elif mangle == "no_prefix":
            ledger_ref = payment_id.replace("pay_", "")
        elif mangle == "truncated":
            ledger_ref = payment_id[:-3]
        else:
            ledger_ref = payment_id.replace("pay_", "pay-")

        gateway_rows.append(gw_row(order_id, payment_id, amount, "captured", captured_at, fee))
        settlement_rows.append(settle_row(utr, round(amount - fee, 2), settlement_date, batch_id_for(settlement_date), payment_id))
        ledger_rows.append(ledger_row(invoice_id, amount, captured_at, ledger_ref))
        add_gt("reference_format_mismatch", order_id, payment_id, utr, invoice_id, "exception_needs_fuzzy_match",
               f"Ledger reference '{ledger_ref}' is a cosmetic variant of payment_id '{payment_id}' "
               "({mangle}). Amount/date match exactly -- a fuzzy-match layer should resolve this "
               "with high confidence.")

    # 8. currency_rounding -- tiny rounding difference in the ledger
    for _ in range(CATEGORY_COUNTS["currency_rounding"]):
        order_id, payment_id = random_id("order_"), random_id("pay_")
        amount = random_amount()
        captured_at = random_capture_time()
        fee = compute_fee(amount)
        settlement_date = captured_at + timedelta(days=2)
        utr = random_utr()
        invoice_id = next_invoice()
        rounding_diff = round(random.uniform(0.01, 0.03), 2)

        gateway_rows.append(gw_row(order_id, payment_id, amount, "captured", captured_at, fee))
        settlement_rows.append(settle_row(utr, round(amount - fee, 2), settlement_date, batch_id_for(settlement_date), payment_id))
        ledger_rows.append(ledger_row(invoice_id, round(amount + rounding_diff, 2), captured_at, payment_id))
        add_gt("currency_rounding", order_id, payment_id, utr, invoice_id, "exception_rounding",
               f"Ledger amount differs from gateway amount by Rs.{rounding_diff} -- a paise-level "
               "rounding artifact. Should be caught by a small tolerance band, not treated as a real mismatch.")

    # 9. true_orphan -- a record with no real counterpart in any other source
    orphan_kinds = ["orphan_settlement", "orphan_ledger", "orphan_gateway_failed"]
    for i in range(CATEGORY_COUNTS["true_orphan"]):
        kind = orphan_kinds[i % len(orphan_kinds)]
        amount = random_amount()
        captured_at = random_capture_time()

        if kind == "orphan_settlement":
            utr = random_utr()
            settlement_date = captured_at + timedelta(days=2)
            settlement_rows.append(settle_row(utr, amount, settlement_date, batch_id_for(settlement_date), random_id("pay_")))
            add_gt("true_orphan", None, None, utr, None, "true_exception_orphan",
                   "Settlement credit with no corresponding gateway payment -- e.g. a misdirected "
                   "bank credit. Genuinely unresolvable from this data alone.")
        elif kind == "orphan_ledger":
            invoice_id = next_invoice()
            ledger_rows.append(ledger_row(invoice_id, amount, captured_at, random_id("pay_")))
            add_gt("true_orphan", None, None, None, invoice_id, "true_exception_orphan",
                   "Manual journal/adjustment entry in the ledger with no gateway transaction behind it.")
        else:
            order_id, payment_id = random_id("order_"), random_id("pay_")
            gateway_rows.append(gw_row(order_id, payment_id, amount, "failed", captured_at, 0.0))
            add_gt("true_orphan", order_id, payment_id, None, None, "true_exception_orphan",
                   "Failed payment attempt -- should be filtered out before reconciliation even starts, "
                   "not chased as a missing settlement.")

    return gateway_rows, settlement_rows, ledger_rows, ground_truth_rows


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    gateway_rows, settlement_rows, ledger_rows, ground_truth_rows = build_dataset(args.seed)

    random.shuffle(gateway_rows)
    random.shuffle(settlement_rows)
    random.shuffle(ledger_rows)

    write_csv(os.path.join(OUTPUT_DIR, "payment_gateway_log.csv"), gateway_rows,
              ["order_id", "payment_id", "amount", "currency", "status", "captured_at", "gateway_fee", "tax"])
    write_csv(os.path.join(OUTPUT_DIR, "bank_settlement_file.csv"), settlement_rows,
              ["utr", "settlement_amount", "settlement_date", "batch_id", "payment_id_ref"])
    write_csv(os.path.join(OUTPUT_DIR, "merchant_ledger.csv"), ledger_rows,
              ["invoice_id", "recorded_amount", "recorded_date", "reference_id"])
    write_csv(os.path.join(OUTPUT_DIR, "ground_truth.csv"), ground_truth_rows,
              ["txn_seq", "category", "order_id", "payment_id", "utr", "invoice_id", "expected_resolution", "notes"])

    print(f"Seed: {args.seed}")
    print(f"Payment Gateway Log rows: {len(gateway_rows)}")
    print(f"Bank Settlement File rows: {len(settlement_rows)}")
    print(f"Merchant Ledger rows: {len(ledger_rows)}")
    print(f"Ground truth transactions: {len(ground_truth_rows)}")
    print("\nCategory breakdown:")
    for cat, count in CATEGORY_COUNTS.items():
        print(f"  {cat}: {count}")
    print(f"\nFiles written to ./{OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
