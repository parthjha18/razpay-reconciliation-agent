"""Layer 1 (deterministic exact-key join) + Layer 2 (arithmetic reconciliation)
for the payment gateway / bank settlement / merchant ledger reconciliation.

No AI, no fuzzy string matching -- exact keys, date windows, and amount
tolerances only. Anything this can't explain with a formula is honestly
flagged for Layer 3/4 rather than guessed at.
"""
from __future__ import annotations

import pandas as pd

from . import constants as c

AUDIT_COLUMNS = [
    "record_type", "order_id", "payment_id", "utr", "invoice_id",
    "layer", "category", "confidence", "reason",
]


def load_sources(data_dir: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    gateway = pd.read_csv(f"{data_dir}/payment_gateway_log.csv")
    settlement = pd.read_csv(f"{data_dir}/bank_settlement_file.csv")
    ledger = pd.read_csv(f"{data_dir}/merchant_ledger.csv")

    gateway["captured_at"] = pd.to_datetime(gateway["captured_at"])
    settlement["settlement_date"] = pd.to_datetime(settlement["settlement_date"])
    ledger["recorded_date"] = pd.to_datetime(ledger["recorded_date"])

    # utr is an all-digit string; pandas silently infers int64 for it (every row is
    # populated, unlike the id columns which mix in blanks and stay object/str). Force
    # it back to str so it joins/compares correctly against string keys elsewhere.
    settlement["utr"] = settlement["utr"].astype(str)
    return gateway, settlement, ledger


def _as_of_date(gateway: pd.DataFrame, settlement: pd.DataFrame, ledger: pd.DataFrame) -> pd.Timestamp:
    """Latest date seen anywhere in the dataset, used as 'today' for pending checks."""
    return max(
        gateway["captured_at"].dt.normalize().max(),
        settlement["settlement_date"].max(),
        ledger["recorded_date"].max(),
    )


def _audit_row(record_type, category, layer, reason, *, order_id="", payment_id="", utr="", invoice_id=""):
    return {
        "record_type": record_type,
        "order_id": order_id,
        "payment_id": payment_id,
        "utr": utr,
        "invoice_id": invoice_id,
        "layer": layer,
        "category": category,
        "confidence": 1.0,
        "reason": reason,
    }


def _dedupe_gateway(gateway: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Collapse duplicate (order_id, payment_id) rows to one representative each.

    Returns the deduped frame plus one audit row per payment_id that had
    duplicates (the underlying transaction is still evaluated using the
    earliest-captured representative row).
    """
    audit_rows = []
    reps = []
    for (order_id, payment_id), group in gateway.groupby(["order_id", "payment_id"], sort=False):
        group = group.sort_values("captured_at")
        reps.append(group.iloc[0])
        if len(group) > 1:
            audit_rows.append(_audit_row(
                "gateway_payment", c.EXCEPTION_DUPLICATE, 1,
                f"Payment logged {len(group)} times in the gateway source with identical "
                f"order_id/payment_id (captured_at differs by "
                f"{(group['captured_at'].max() - group['captured_at'].min()).seconds}s). "
                "Deduplicated to one representative row before matching.",
                order_id=order_id, payment_id=payment_id,
            ))
    deduped = pd.DataFrame(reps).reset_index(drop=True)
    return deduped, audit_rows


def _classify_settlement(gw_row, settlement_match) -> tuple[str, str, int]:
    """Returns (category, reason, layer) for the settlement side of a gateway record."""
    if settlement_match is None:
        return None, None, None

    expected = round(gw_row["amount"] - gw_row["gateway_fee"] - gw_row["tax"], 2)
    actual = round(settlement_match["settlement_amount"], 2)
    diff = round(actual - expected, 2)
    date_gap = (settlement_match["settlement_date"] - gw_row["captured_at"].normalize()).days

    if abs(diff) <= c.ROUNDING_TOLERANCE:
        if date_gap <= c.NORMAL_SETTLEMENT_WINDOW_DAYS:
            return c.MATCHED_LAYER1_2, (
                f"Exact payment_id join; settlement (Rs.{actual}) matches amount minus gateway "
                f"fee/tax (Rs.{expected}) and landed {date_gap}d after capture (within the "
                f"T+{c.NORMAL_SETTLEMENT_WINDOW_DAYS} window)."
            ), 1
        return c.MATCHED_EXTENDED_WINDOW, (
            f"Exact payment_id join and settlement amount reconciles exactly (Rs.{actual} = "
            f"Rs.{expected}), but it landed {date_gap}d after capture -- outside the normal "
            f"T+{c.NORMAL_SETTLEMENT_WINDOW_DAYS} window. Genuine match, just late."
        ), 1

    if gw_row["status"] == "partially_refunded":
        return c.EXCEPTION_REFUND_MISMATCH, (
            f"Gateway status is 'partially_refunded'. Settlement (Rs.{actual}) is short of the "
            f"gross amount-minus-fee (Rs.{expected}) by Rs.{abs(diff)}, consistent with a refund "
            "issued after capture. Ledger likely still shows the gross amount -- needs Layer 3/4 "
            "to confirm the refund amount and reconcile the ledger."
        ), 2

    return c.EXCEPTION_FEE_MISMATCH, (
        f"Settlement (Rs.{actual}) differs from amount-minus-fee/tax (Rs.{expected}) by "
        f"Rs.{abs(diff)}, not explained by the standard fee formula or rounding tolerance -- "
        "possibly an unreflected deduction (e.g. TDS). Needs Layer 3/4 reasoning."
    ), 2


def run_layer_1_2(gateway: pd.DataFrame, settlement: pd.DataFrame, ledger: pd.DataFrame) -> pd.DataFrame:
    as_of = _as_of_date(gateway, settlement, ledger)
    audit_rows: list[dict] = []

    # --- Failed payments never entered reconciliation. ---
    failed = gateway[gateway["status"] == "failed"]
    for _, row in failed.iterrows():
        audit_rows.append(_audit_row(
            "gateway_payment", c.TRUE_EXCEPTION_ORPHAN, 1,
            "Payment attempt failed at the gateway -- excluded from settlement/ledger "
            "reconciliation rather than chased as a missing settlement.",
            order_id=row["order_id"], payment_id=row["payment_id"],
        ))

    active = gateway[gateway["status"] != "failed"]
    deduped, dup_rows = _dedupe_gateway(active)
    audit_rows.extend(dup_rows)

    settlement_by_payment = {row["payment_id_ref"]: row for _, row in settlement.iterrows()}
    ledger_by_reference = {row["reference_id"]: row for _, row in ledger.iterrows()}
    claimed_ledger_refs: set[str] = set()

    for _, gw_row in deduped.iterrows():
        payment_id = gw_row["payment_id"]
        settlement_match = settlement_by_payment.get(payment_id)
        ledger_match = ledger_by_reference.get(payment_id)
        if ledger_match is not None:
            claimed_ledger_refs.add(payment_id)

        if settlement_match is None:
            days_since_capture = (as_of - gw_row["captured_at"].normalize()).days
            if days_since_capture <= c.PENDING_SETTLEMENT_WINDOW_DAYS:
                audit_rows.append(_audit_row(
                    "gateway_payment", c.EXCEPTION_PENDING_SETTLEMENT, 1,
                    f"Captured {days_since_capture}d ago (as of {as_of.date()}) -- too recent "
                    "for settlement to have landed. Pending, not lost.",
                    order_id=gw_row["order_id"], payment_id=payment_id,
                ))
            else:
                audit_rows.append(_audit_row(
                    "gateway_payment", c.EXCEPTION_UNCLASSIFIED, 2,
                    f"Captured {days_since_capture}d ago with no matching settlement -- outside "
                    "the normal pending window. Cannot be explained deterministically; escalate "
                    "to Layer 4.",
                    order_id=gw_row["order_id"], payment_id=payment_id,
                ))
            continue

        category, reason, layer = _classify_settlement(gw_row, settlement_match)

        if category in (c.MATCHED_LAYER1_2, c.MATCHED_EXTENDED_WINDOW):
            if ledger_match is None:
                audit_rows.append(_audit_row(
                    "gateway_payment", c.EXCEPTION_NEEDS_FUZZY_MATCH, 3,
                    "Gateway and settlement reconcile exactly, but no ledger row has a "
                    f"reference_id exactly equal to payment_id '{payment_id}'. Needs Layer 3 "
                    "fuzzy matching against ledger reference_id formatting variants.",
                    order_id=gw_row["order_id"], payment_id=payment_id,
                    utr=settlement_match["utr"],
                ))
                continue

            ledger_diff = round(abs(ledger_match["recorded_amount"] - gw_row["amount"]), 2)
            if ledger_diff <= 0.005:
                audit_rows.append(_audit_row(
                    "gateway_payment", category, layer, reason,
                    order_id=gw_row["order_id"], payment_id=payment_id,
                    utr=settlement_match["utr"], invoice_id=ledger_match["invoice_id"],
                ))
            elif ledger_diff <= c.ROUNDING_TOLERANCE:
                audit_rows.append(_audit_row(
                    "gateway_payment", c.EXCEPTION_ROUNDING, 2,
                    f"Settlement reconciles cleanly, but ledger amount (Rs.{ledger_match['recorded_amount']}) "
                    f"differs from gateway amount (Rs.{gw_row['amount']}) by Rs.{ledger_diff} -- a "
                    "paise-level rounding artifact within tolerance, not a real mismatch.",
                    order_id=gw_row["order_id"], payment_id=payment_id,
                    utr=settlement_match["utr"], invoice_id=ledger_match["invoice_id"],
                ))
            else:
                audit_rows.append(_audit_row(
                    "gateway_payment", c.EXCEPTION_UNCLASSIFIED, 2,
                    f"Settlement reconciles cleanly, but ledger amount differs from gateway "
                    f"amount by Rs.{ledger_diff} -- beyond rounding tolerance and not explained "
                    "by a known formula. Escalate to Layer 4.",
                    order_id=gw_row["order_id"], payment_id=payment_id,
                    utr=settlement_match["utr"], invoice_id=ledger_match["invoice_id"],
                ))
        else:
            audit_rows.append(_audit_row(
                "gateway_payment", category, layer, reason,
                order_id=gw_row["order_id"], payment_id=payment_id,
                utr=settlement_match["utr"],
                invoice_id=ledger_match["invoice_id"] if ledger_match is not None else "",
            ))

    # --- Settlement rows whose payment_id_ref matches no known gateway payment at all. ---
    known_payment_ids = set(deduped["payment_id"]) | set(failed["payment_id"])
    for _, s_row in settlement.iterrows():
        if s_row["payment_id_ref"] not in known_payment_ids:
            audit_rows.append(_audit_row(
                "settlement_orphan", c.TRUE_EXCEPTION_ORPHAN, 1,
                f"Settlement credit (utr {s_row['utr']}) references payment_id "
                f"'{s_row['payment_id_ref']}', which does not exist in the gateway log -- "
                "e.g. a misdirected bank credit. Genuinely unresolvable from this data alone.",
                utr=s_row["utr"],
            ))

    # --- Ledger rows with no exact reference_id match anywhere. Could be a true orphan
    # or a formatting variant of a real payment_id -- Layer 1-2 can't tell which without
    # fuzzy matching, so both are deferred to Layer 3 rather than guessed. ---
    for _, l_row in ledger.iterrows():
        ref = l_row["reference_id"]
        if ref in claimed_ledger_refs:
            continue
        audit_rows.append(_audit_row(
            "ledger_orphan", c.EXCEPTION_NEEDS_FUZZY_MATCH, 3,
            f"Ledger reference '{ref}' (invoice {l_row['invoice_id']}) has no exact match "
            "among known payment_ids. May be a cosmetic formatting variant of a real payment "
            "(needs Layer 3 fuzzy match) or a true orphan entry (needs Layer 4 classification) "
            "-- not distinguishable by exact-key logic alone.",
            invoice_id=l_row["invoice_id"],
        ))

    return pd.DataFrame(audit_rows, columns=AUDIT_COLUMNS)
