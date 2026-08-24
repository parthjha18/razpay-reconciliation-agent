# Multi-Source Payment Reconciliation Agent

Razorpay Buildathon — Track 04: AI Finance Controller

Matches records across a payment gateway log, a bank settlement file, and a
merchant ledger; reports a match rate; and produces a categorized, explained
list of exceptions it couldn't resolve. Built as escalating layers so AI is
used only where deterministic logic genuinely can't do the job — see
[CLAUDE.md](CLAUDE.md) for the full build brief.

## Status

- [x] Synthetic data generator (`data/generate_data.py`)
- [x] Layer 1-2: deterministic exact-key join + arithmetic (fee/TDS/rounding) reconciliation
- [ ] Layer 3-4: AI-assisted fuzzy matching + exception classification
- [ ] Audit trail viewer
- [ ] Deliberate failure-handling demo
- [ ] React dashboard

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Regenerate the synthetic dataset

```bash
cd data && python generate_data.py --seed 42
```

## Run the Layer 1-2 matching engine

```bash
python scripts/run_matching_engine.py
```

## Validate against ground truth

```bash
python scripts/validate_against_ground_truth.py
```
