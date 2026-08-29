"""Deterministic heuristic fallback for Layer 3 fuzzy matching.

Activated when the Gemini API is unavailable or rate-limited -- degrades to a
structural string comparison instead of hanging or failing completely.

The heuristic strips the 'pay_' prefix, case-folds, and removes separators,
then checks for exact equality on the normalized forms. Only that strongest case
resolves to is_match=True (confidence 0.85) so the caller's 0.75 threshold still
gates it. Anything weaker is returned as is_match=False so the caller defers to
Layer 4 rather than guessing; the confidence value still reflects how close the
strings were, giving Layer 4 context about why it ended up there.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

_PREFIX_RE = re.compile(r"^pay[-_]?", re.IGNORECASE)
_SEPARATOR_RE = re.compile(r"[-_.\s]+")


def _normalize(s: str) -> str:
    s = _PREFIX_RE.sub("", s)
    s = _SEPARATOR_RE.sub("", s)
    return s.lower().strip()


def heuristic_match(ledger_ref: str, payment_id: str) -> dict:
    """Return the same schema as ai_client.call_tool for Layer 3.

    {"is_match": bool, "confidence": float, "reason": str}
    """
    norm_ref = _normalize(ledger_ref)
    norm_pid = _normalize(payment_id)

    if norm_ref == norm_pid:
        return {
            "is_match": True,
            "confidence": 0.85,
            "reason": (
                f"Heuristic (AI unavailable): normalized forms identical ('{norm_ref}') -- "
                f"the ledger reference is a case/prefix/separator variant of the payment_id."
            ),
        }

    # Containment: one is a truncated/prefixed version of the other.
    # Guard against short tokens matching inside random strings.
    shorter = min(norm_ref, norm_pid, key=len)
    longer = max(norm_ref, norm_pid, key=len)
    if len(shorter) >= 8 and shorter in longer:
        return {
            "is_match": False,
            "confidence": 0.65,
            "reason": (
                f"Heuristic (AI unavailable): one string contains the other after normalization "
                f"but requires AI confirmation; deferring to Layer 4."
            ),
        }

    ratio = SequenceMatcher(None, norm_ref, norm_pid).ratio()
    # Cap heuristic similarity below the 0.75 acceptance threshold so a
    # near-but-not-identical pair never gets silently promoted to a match.
    confidence = round(ratio * 0.7, 2)
    return {
        "is_match": False,
        "confidence": confidence,
        "reason": (
            f"Heuristic (AI unavailable): strings differ after normalization "
            f"(similarity {ratio:.2f}); deferring to Layer 4."
        ),
    }
