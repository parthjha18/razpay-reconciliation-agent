"""Layer 3 -- AI-assisted fuzzy matching.

Only touches what Layer 1-2 explicitly couldn't resolve: ledger rows with no
exact reference_id match, and the gateway/settlement pairs that reconciled
cleanly but never found their ledger counterpart. A deterministic amount
prefilter runs first -- if no gateway candidate is within tolerance of a
ledger row's amount, there is nothing to propose and the LLM is not called
at all (an obvious non-match should cost zero tokens). Only a genuine
one-candidate ambiguity (same amount, different reference string) goes to
the model, which must return a confidence score and a reason; anything
below the threshold -- or any candidate set that isn't exactly one -- is
left for Layer 4 rather than guessed at.
"""
from __future__ import annotations

import pandas as pd

from . import constants as c
from .ai_client import LLMCallFailed, call_tool
from .heuristic_fuzzy import heuristic_match

CONFIDENCE_THRESHOLD = 0.75

# Mangled reference_ids (lowercase/no-prefix/truncated/dashes) never touch the
# amount, so an exact-cents match is the right bar here -- not a rounding band.
AMOUNT_CANDIDATE_TOLERANCE = 0.01

MATCH_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "is_match": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string", "description": "One sentence justifying the decision."},
    },
    "required": ["is_match", "confidence", "reason"],
}

SYSTEM_PROMPT = (
    "You are a payments reconciliation analyst. You will be shown a merchant ledger "
    "reference string and a single candidate gateway payment_id that already has a "
    "matching amount. Decide whether the ledger reference is plausibly a cosmetic "
    "formatting variant of that exact payment_id (case change, missing 'pay_' prefix, "
    "truncation, or a different separator) referring to the SAME transaction -- as "
    "opposed to an unrelated transaction that merely happens to share an amount. "
    "Judge only the string relationship; amount and date proximity are already confirmed."
)


def _propose(ledger_ref: str, invoice_id: str, recorded_amount: float, recorded_date,
             payment_id: str, gw_amount: float, captured_at) -> dict:
    return call_tool(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=(
            f"Ledger reference_id: {ledger_ref!r} (invoice {invoice_id}, "
            f"amount {recorded_amount}, recorded_date {recorded_date})\n"
            f"Candidate gateway payment_id: {payment_id!r} "
            f"(amount {gw_amount}, captured_at {captured_at})"
        ),
        tool_name="propose_ledger_match",
        tool_description="Propose whether the ledger reference matches the candidate payment_id.",
        input_schema=MATCH_TOOL_SCHEMA,
    )


def run_layer_3(audit: pd.DataFrame, gateway: pd.DataFrame, ledger: pd.DataFrame) -> pd.DataFrame:
    audit = audit.reset_index(drop=True).copy()
    gw_by_payment_id = gateway.set_index("payment_id")
    ledger_by_invoice = ledger.set_index("invoice_id")

    ledger_idxs = audit.index[
        (audit["record_type"] == "ledger_orphan") & (audit["category"] == c.EXCEPTION_NEEDS_FUZZY_MATCH)
    ]
    gw_idxs = audit.index[
        (audit["record_type"] == "gateway_payment") & (audit["category"] == c.EXCEPTION_NEEDS_FUZZY_MATCH)
    ]
    gw_candidates = [(idx, audit.loc[idx, "payment_id"]) for idx in gw_idxs]

    rows_to_drop = []
    new_rows = []

    for l_idx in ledger_idxs:
        invoice_id = audit.loc[l_idx, "invoice_id"]
        l_data = ledger_by_invoice.loc[invoice_id]

        matches = [
            (idx, pid) for idx, pid in gw_candidates
            if abs(gw_by_payment_id.loc[pid, "amount"] - l_data["recorded_amount"]) <= AMOUNT_CANDIDATE_TOLERANCE
        ]

        if len(matches) != 1:
            reason = (
                "no gateway candidate within amount tolerance" if not matches
                else f"{len(matches)} gateway candidates share this amount -- ambiguous"
            )
            audit.loc[l_idx, "reason"] += f" [Layer 3: {reason}; deferred to Layer 4 without guessing.]"
            continue

        gw_idx, payment_id = matches[0]
        gw_data = gw_by_payment_id.loc[payment_id]

        is_heuristic = False
        try:
            result = _propose(
                l_data["reference_id"], invoice_id, l_data["recorded_amount"], l_data["recorded_date"].date(),
                payment_id, gw_data["amount"], gw_data["captured_at"],
            )
        except LLMCallFailed as exc:
            result = heuristic_match(l_data["reference_id"], payment_id)
            is_heuristic = True
            if result["is_match"]:
                for i in [l_idx, gw_idx]:
                    audit.loc[i, "reason"] += (
                        f" [Layer 3: Gemini unavailable ({exc}); heuristic fallback matched at "
                        f"confidence {result['confidence']:.2f}.]"
                    )
            else:
                for i in [l_idx, gw_idx]:
                    audit.loc[i, "reason"] += (
                        f" [Layer 3: Gemini unavailable ({exc}); heuristic confidence "
                        f"{result['confidence']:.2f} insufficient -- deferred to Layer 4.]"
                    )

        source_label = "heuristic fallback" if is_heuristic else "AI"
        if result["is_match"] and result["confidence"] >= CONFIDENCE_THRESHOLD:
            rows_to_drop.extend([l_idx, gw_idx])
            new_rows.append({
                "record_type": "fuzzy_matched_transaction",
                "order_id": audit.loc[gw_idx, "order_id"],
                "payment_id": payment_id,
                "utr": audit.loc[gw_idx, "utr"],
                "invoice_id": invoice_id,
                "layer": 3,
                "category": c.MATCHED_LAYER3,
                "confidence": result["confidence"],
                "reason": (
                    f"Layer 3 {source_label} match (confidence {result['confidence']:.2f}): {result['reason']} "
                    f"Ledger reference '{l_data['reference_id']}' resolved to payment_id '{payment_id}'."
                ),
            })
        elif not is_heuristic:
            note = (
                f" [Layer 3: candidate '{payment_id}' reviewed by {source_label}, confidence "
                f"{result['confidence']:.2f} below {CONFIDENCE_THRESHOLD} threshold "
                f"({result['reason']}); deferred to Layer 4.]"
            )
            audit.loc[l_idx, "reason"] += note
            audit.loc[gw_idx, "reason"] += note

    audit = audit.drop(index=rows_to_drop)
    if new_rows:
        audit = pd.concat([audit, pd.DataFrame(new_rows)], ignore_index=True)
    return audit.reset_index(drop=True)
