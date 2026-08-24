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
      schema-constrained structured output) — logic verified by mocked-LLM tests
      and live end-to-end runs
- [x] Audit trail (per-record CSV + CLI report, one line per record with which layer
      resolved it, confidence, and a plain-language reason)
- [x] Deliberate failure handling: malformed records → flagged for manual review, not
      dropped/crashed on; a Layer 3/4 LLM error or timeout falls back to the next layer
      instead of hanging or guessing (`tests/test_failure_handling.py`)

Phase 2 (not started): React dashboard, re-running against fresh seeds, threshold
tuning, architecture diagram, demo recording.

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

## Run tests

```bash
pytest
```
