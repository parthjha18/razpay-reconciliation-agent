# Multi-Source Payment Reconciliation Agent

**Razorpay Buildathon 2026 — Track 04: AI Finance Controller**

Automates payment reconciliation across three systems that are supposed to agree and rarely do: a payment gateway log, a bank settlement file, and a merchant ledger. The agent matches records across all three sources, reports a match rate, and produces a categorized, explained list of exceptions it couldn't resolve — not just "these don't match" but *why*.

Built as four escalating layers so AI is used only where deterministic logic genuinely can't do the job.

---

## Architecture

| Layer | What it does | Uses AI? |
|---|---|---|
| **Layer 1** | Exact-key join on payment IDs within a date window and amount tolerance | No |
| **Layer 2** | Arithmetic reconciliation: amount − fee − tax = settlement, within rounding tolerance | No |
| **Layer 3** | Fuzzy matching for reference ID format variants (e.g. `PAY_ABC123` vs `pay-abc-123`) — model proposes a match with confidence score; anything below 0.75 defers to Layer 4 | Yes (Gemini) |
| **Layer 4** | Exception classification and plain-language explanation for audit trail | Yes (Gemini) |

Layer 3 also has a deterministic heuristic fallback (string normalization + edit distance) that activates when the Gemini API is unavailable, so the system degrades gracefully rather than failing.

---

## Results

- **Layer 1-2 only:** 98.4% transaction accuracy vs. held-out ground truth, 100% on required gate categories (`clean_match`, `fee_tds_deduction`)
- **Full pipeline (Layers 1-4):** 100% transaction accuracy across all 9 exception categories — mismatches: none
- **Throughput:** ~0.2 ms per record (Layer 1-2, benchmarked at 100k rows) — 5,000 transactions/month clears in ~1.2 s vs. ~250 analyst-hours manually
- **Robustness:** re-ran on two unseen seeds (seed 7, seed 99) — 98.4% and 96.8% overall, 100% on gate both times

---

## Exception categories handled

- Timing difference (settlement lands T+2 days)
- Fee / TDS deduction (arithmetic reconciliation)
- Duplicate entry
- Missing / pending settlement
- Partial refund mismatch
- Reference format mismatch (fuzzy match via Layer 3)
- Currency rounding (paise-level tolerance)
- True orphan (no counterpart in any source)
- Malformed record (flagged for manual review, not dropped)

---

## Deliverables

- [x] Synthetic data generator — regeneratable: `cd data && python generate_data.py --seed 42`
- [x] Layer 1-2 deterministic matching engine with ground truth validation
- [x] Layer 3-4 AI-assisted fuzzy matching + exception classification (Gemini API)
- [x] Deterministic heuristic fallback for Layer 3 when API unavailable
- [x] Audit trail — per-record CSV with layer, category, confidence, plain-language reason
- [x] Deliberate failure handling — malformed records flagged, LLM errors fall back gracefully
- [x] React (Vite) dashboard — Summary, Sources, Exceptions, filterable Audit Trail
- [x] Architecture diagram (`docs/architecture.md`)
- [x] Pitch script (`docs/pitch_script.md`)
- [x] Layer 1-2 throughput benchmark (`scripts/benchmark_layer1_2.py`)

---

## Setup

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add your `GEMINI_API_KEY` (needed for Layers 3-4).

---

## Regenerate the dataset

```bash
cd data && python generate_data.py --seed 42
```

## Run Layer 1-2 only (fast, no API key needed)

```bash
python scripts/run_matching_engine.py
python scripts/validate_against_ground_truth.py
```

## Run the full Layer 1-4 pipeline

```bash
python scripts/run_pipeline.py
python scripts/validate_full_pipeline.py
```

Needs `GEMINI_API_KEY`. Free tier is 5 req/min — the pipeline paces itself, expect a few minutes.

## Benchmark Layer 1-2 throughput

```bash
python scripts/benchmark_layer1_2.py
```

## Run tests

```bash
pytest
```

## Run the dashboard

```bash
# Terminal 1
uvicorn backend.main:app --port 8000

# Terminal 2
cd frontend && npm install && npm run dev
```

Open `http://localhost:5173`. Run the pipeline first (or use the "Re-run" buttons in the Summary tab).
