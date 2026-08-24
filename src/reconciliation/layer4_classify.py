"""Layer 4 -- exception classification + plain-language explanation.

Runs only on the categories Layer 1-3 explicitly couldn't close out with
certainty (see constants.LAYER4_ELIGIBLE_CATEGORIES) -- clean matches,
duplicates, pending settlements, and rounding already have a sufficient
deterministic explanation and are left alone. For each eligible record the
model is given Layer 1-3's own finding as a prior and asked to confirm or
override it from a fixed enum, plus write a one-to-two sentence explanation
for a non-technical auditor. An override is only accepted above a stricter
confidence bar than a confirmation needs, so a mediocre LLM response can't
quietly overwrite a deterministic finding; a failed/timeouts call leaves the
category untouched and says so in the reason, per the same fallback
contract as Layer 3.
"""
from __future__ import annotations

import pandas as pd

from . import constants as c
from .ai_client import LLMCallFailed, call_tool

OVERRIDE_CONFIDENCE_THRESHOLD = 0.8

CLASSIFY_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "enum": [
                "fee_or_tds_deduction", "refund_adjustment", "duplicate",
                "missing_pending_settlement", "true_orphan", "needs_manual_review",
            ],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "explanation": {
            "type": "string",
            "description": "1-2 plain-language sentences for a financial-ops auditor, citing the actual numbers.",
        },
    },
    "required": ["category", "confidence", "explanation"],
}

LABEL_TO_CATEGORY = {
    "fee_or_tds_deduction": c.EXCEPTION_FEE_MISMATCH,
    "refund_adjustment": c.EXCEPTION_REFUND_MISMATCH,
    "duplicate": c.EXCEPTION_DUPLICATE,
    "missing_pending_settlement": c.EXCEPTION_PENDING_SETTLEMENT,
    "true_orphan": c.TRUE_EXCEPTION_ORPHAN,
    "needs_manual_review": c.EXCEPTION_MANUAL_REVIEW,
}

SYSTEM_PROMPT = (
    "You are a payments reconciliation analyst writing the audit trail entry for one "
    "exception a deterministic rules engine could not fully resolve. You are given the "
    "rules engine's own prior finding and evidence. Confirm that finding, or override it "
    "only if the evidence clearly points elsewhere. Then write a short, plain-language "
    "explanation a non-technical finance reviewer can act on."
)


def _classify(record_summary: str) -> dict:
    return call_tool(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=record_summary,
        tool_name="classify_exception",
        tool_description="Classify this reconciliation exception and explain it in plain language.",
        input_schema=CLASSIFY_TOOL_SCHEMA,
    )


def _record_summary(row: pd.Series) -> str:
    keys = ", ".join(
        f"{k}={row[k]}" for k in ("order_id", "payment_id", "utr", "invoice_id") if row[k]
    )
    return (
        f"Record: {keys}\n"
        f"Rules engine's prior category: {row['category']}\n"
        f"Rules engine's evidence: {row['reason']}"
    )


def run_layer_4(audit: pd.DataFrame) -> pd.DataFrame:
    audit = audit.reset_index(drop=True).copy()
    eligible = audit.index[audit["category"].isin(c.LAYER4_ELIGIBLE_CATEGORIES)]

    for idx in eligible:
        row = audit.loc[idx]
        prior_category = row["category"]
        try:
            result = _classify(_record_summary(row))
        except LLMCallFailed as exc:
            audit.loc[idx, "reason"] += (
                f" [Layer 4 LLM call failed ({exc}); retained Layer {int(row['layer'])}'s "
                "deterministic classification without an AI explanation.]"
            )
            continue

        proposed_category = LABEL_TO_CATEGORY[result["category"]]
        confidence = result["confidence"]

        if proposed_category == prior_category or confidence >= OVERRIDE_CONFIDENCE_THRESHOLD:
            final_category = proposed_category
        else:
            final_category = prior_category

        audit.loc[idx, "category"] = final_category
        audit.loc[idx, "layer"] = 4
        audit.loc[idx, "confidence"] = confidence
        audit.loc[idx, "reason"] = (
            f"{result['explanation']} "
            f"[Layer 4, confidence {confidence:.2f}; prior Layer {int(row['layer'])} finding: {row['reason']}]"
        )

    return audit
