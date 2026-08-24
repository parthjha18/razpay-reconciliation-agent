"""Smoke tests for the dashboard's FastAPI backend."""
import os
import sys

import pandas as pd
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from main import app  # noqa: E402

client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_sources_returns_all_three_files():
    response = client.get("/api/sources")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"gateway", "settlement", "ledger"}
    assert len(body["gateway"]) > 0


def test_rerun_layer12_then_summary_reflects_it():
    rerun = client.post("/api/rerun/layer1-2")
    assert rerun.status_code == 200
    assert rerun.json()["total_records"] > 0

    summary = client.get("/api/summary")
    assert summary.status_code == 200
    assert summary.json()["source"] == "audit_trail_l1_l2.csv"


def test_audit_trail_filters_by_category():
    client.post("/api/rerun/layer1-2")
    response = client.get("/api/audit-trail", params={"category": "matched_layer1_2"})
    assert response.status_code == 200
    rows = response.json()["rows"]
    assert len(rows) > 0
    assert all(r["category"] == "matched_layer1_2" for r in rows)


def test_summary_without_any_audit_trail_returns_404(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import main as backend_main
    monkeypatch.setattr(backend_main, "FULL_AUDIT_PATH", str(tmp_path / "full.csv"))
    monkeypatch.setattr(backend_main, "L1_2_AUDIT_PATH", str(tmp_path / "l1_2.csv"))
    response = client.get("/api/summary")
    assert response.status_code == 404
