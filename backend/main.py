"""FastAPI backend for the reconciliation dashboard.

Serves the checked-in sources and the most recently generated audit trail
as JSON, and exposes endpoints to re-run the pipeline on demand. Layer 1-2
reruns are fast and free; a full Layer 1-4 rerun calls Gemini per exception
and can take a while on the free tier's 5-requests/minute cap -- the
frontend is expected to show that as a loading state, not assume it's instant.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reconciliation import constants as c  # noqa: E402
from reconciliation import engine  # noqa: E402
from reconciliation.pipeline import run_full_pipeline  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")
FULL_AUDIT_PATH = os.path.join(OUTPUT_DIR, "audit_trail_full.csv")
L1_2_AUDIT_PATH = os.path.join(OUTPUT_DIR, "audit_trail_l1_l2.csv")

app = FastAPI(title="Reconciliation Dashboard API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://{host}:{port}"
        for host in ("localhost", "127.0.0.1")
        for port in (5173, 5174, 5175)
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _latest_audit_path() -> str:
    if os.path.exists(FULL_AUDIT_PATH):
        return FULL_AUDIT_PATH
    if os.path.exists(L1_2_AUDIT_PATH):
        return L1_2_AUDIT_PATH
    raise HTTPException(404, "No audit trail found -- run POST /api/rerun/layer1-2 first")


def _summary(audit: pd.DataFrame) -> dict:
    total = len(audit)
    matched = int(audit["category"].isin(c.MATCHED_CATEGORIES).sum())
    return {
        "total_records": total,
        "matched": matched,
        "match_rate": round(matched / total, 4) if total else 0.0,
        "category_breakdown": audit["category"].value_counts().to_dict(),
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/sources")
def sources():
    gateway, settlement, ledger = engine.load_sources(DATA_DIR)
    return {
        "gateway": _df_to_records(gateway),
        "settlement": _df_to_records(settlement),
        "ledger": _df_to_records(ledger),
    }


@app.get("/api/summary")
def summary():
    audit = pd.read_csv(_latest_audit_path(), keep_default_na=False)
    return {"source": os.path.basename(_latest_audit_path()), **_summary(audit)}


@app.get("/api/audit-trail")
def audit_trail(
    category: Optional[str] = Query(None),
    record_type: Optional[str] = Query(None),
    layer: Optional[int] = Query(None),
):
    audit = pd.read_csv(_latest_audit_path(), keep_default_na=False)
    if category:
        audit = audit[audit["category"] == category]
    if record_type:
        audit = audit[audit["record_type"] == record_type]
    if layer is not None:
        audit = audit[audit["layer"] == layer]
    return {"source": os.path.basename(_latest_audit_path()), "rows": _df_to_records(audit)}


@app.post("/api/rerun/layer1-2")
def rerun_layer1_2():
    gateway, settlement, ledger = engine.load_sources(DATA_DIR)
    audit = engine.run_layer_1_2(gateway, settlement, ledger)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    audit.to_csv(L1_2_AUDIT_PATH, index=False)
    if os.path.exists(FULL_AUDIT_PATH):
        os.remove(FULL_AUDIT_PATH)  # stale relative to the new Layer 1-2 pass
    return _summary(audit)


@app.post("/api/rerun/full")
def rerun_full():
    audit = run_full_pipeline(DATA_DIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    audit.to_csv(FULL_AUDIT_PATH, index=False)
    return _summary(audit)
