# Multi-Source Payment Reconciliation Agent

Razorpay Buildathon — Track 04: AI Finance Controller

Matches records across a payment gateway log, a bank settlement file, and a
merchant ledger; reports a match rate; and produces a categorized, explained
list of exceptions it couldn't resolve. Built as escalating layers so AI is
used only where deterministic logic genuinely can't do the job — see
[CLAUDE.md](CLAUDE.md) for the full build brief.

## Status

Phase 1 (CLAUDE.md section 7) is done:

- [x] Synthetic data generator (`data/generate_data.py`)
- [x] Layer 1-2: deterministic exact-key join + arithmetic (fee/TDS/rounding) reconciliation
      — 98.4% transaction accuracy vs. `data/ground_truth.csv`, 100% on the required
      `clean_match` + `fee_tds_deduction` gate (see `reports/phase1_layer1_2_validation.md`)
- [x] Layer 3-4: AI-assisted fuzzy matching + exception classification (Gemini API,
      schema-constrained structured output) — **100% full-pipeline transaction
      accuracy on a live run** against real Gemini calls (see
      `reports/full_pipeline_validation.md`), plus mocked-LLM tests for logic
      correctness independent of API availability
- [x] Audit trail (per-record CSV + CLI report, one line per record with which layer
      resolved it, confidence, and a plain-language reason)
- [x] Deliberate failure handling: malformed records → flagged for manual review, not
      dropped/crashed on; a Layer 3/4 LLM error or timeout falls back to the next layer
      instead of hanging or guessing (`tests/test_failure_handling.py`)

Phase 2 (in progress):

- [x] React (Vite) dashboard + FastAPI backend — Summary, Sources, Exceptions
      (grouped by category), and a filterable Audit Trail, with on-demand reruns
- [x] Re-ran Layer 1-2 against two fresh, previously-unseen seeds (`--seed 7`,
      `--seed 99`): 98.4% and 96.8% overall, 100% on the gate both times — same
      single known edge case both runs, not a new failure mode on fresh data
- [x] Architecture diagram (`docs/architecture.md`) and 5-minute pitch script
      (`docs/pitch_script.md`)
- [ ] Confidence threshold / tolerance-band tuning based on what actually misfires
- [ ] Demo recording

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Layer 3-4 need `GEMINI_API_KEY` set in the environment (or copy `.env.example`
to `.env` and fill it in).

## Regenerate the synthetic dataset

```bash
cd data && python generate_data.py --seed 42
```

## Run the Layer 1-2 matching engine only

```bash
python scripts/run_matching_engine.py
```

## Validate Layer 1-2 against ground truth

```bash
python scripts/validate_against_ground_truth.py
```

## Run the full Layer 1-4 pipeline

```bash
python scripts/run_pipeline.py
```

Needs `GEMINI_API_KEY`. The free tier caps this model at 5 requests/minute,
so a full run takes a few minutes (paced deliberately — see
`src/reconciliation/ai_client.py`), not because anything is stuck.

## Validate the full pipeline against ground truth

```bash
python scripts/validate_full_pipeline.py
```

Run `run_pipeline.py` first. Scores full-pipeline correctness (a reference-
format mismatch is right whether Layer 3 resolved it or correctly deferred
it) rather than the exact Layer-1-2-only label `validate_against_ground_truth.py` checks.

## Run tests

```bash
pytest
```

## Run the dashboard (backend + frontend)

```bash
# Terminal 1 -- backend (serves data/ and output/, exposes rerun endpoints)
uvicorn backend.main:app --port 8000

# Terminal 2 -- frontend
cd frontend && npm install && npm run dev
```

Open the URL Vite prints (usually http://localhost:5173). The dashboard reads
whichever audit trail CSV was generated most recently in `output/` — run one
of the scripts above first, or use the "Re-run" buttons in the Summary tab.
