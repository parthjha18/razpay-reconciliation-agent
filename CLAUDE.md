# Razorpay Buildathon — Track 04: AI Finance Controller
## Build Brief: Multi-Source Payment Reconciliation Agent

**Deadline:** Sept 5, 2026 · **Submission:** Public GitHub repo + 5-min pitch + architecture doc
**Judged on:** Problem Taste · Build Quality · AI Judgment · Failure Recovery

---

## 1. The scenario

A merchant's money moves through three systems that should agree with each other but rarely do cleanly:

1. **Payment Gateway Log** — what the gateway (Razorpay-style) recorded when the customer paid
2. **Bank Settlement File** — what actually landed in the merchant's bank account, net of fees, often batched and delayed
3. **Merchant Ledger** — what the merchant's internal accounting system recorded as revenue

The agent's job: match records across all three sources, report a match rate, and produce an **honest, categorized list of exceptions** it couldn't resolve — not just "these don't match" but *why*.

This mirrors real financial-ops reconciliation work (PCAMI Finance MI style) — Cognos/ledger vs system-of-record vs actuals — just scoped to a payments context that's directly on-brand for Razorpay.

---

## 2. Data model (synthetic, ≥50 records, with known ground truth)

Build a generator that creates matched triples **and** deliberately plants mismatches, so your match-rate number is provable, not cherry-picked. Keep a hidden "ground truth" label per record (matched / exception-type) to validate your own pipeline before demo day.

**Source A — Payment Gateway Log**
`order_id, payment_id, amount, currency, status, captured_at, gateway_fee, tax`

**Source B — Bank Settlement File**
`utr, settlement_amount, settlement_date, batch_id, payment_id_ref`

**Source C — Merchant Ledger**
`invoice_id, recorded_amount, recorded_date, reference_id`

**Planted exception categories** (build ~6-8 of each, so the exception list is substantive):
- **Timing difference** — payment captured, settlement lands 2-3 days later (still resolvable, not a real problem)
- **Fee/TDS deduction** — settlement_amount = amount − gateway_fee − tax (needs arithmetic reconciliation, not just equality)
- **Duplicate entry** — same payment logged twice in one source
- **Missing settlement** — payment captured, no settlement record yet (genuinely pending)
- **Partial/refund mismatch** — partial refund issued after capture, settlement reflects net amount
- **Reference typo/format mismatch** — same transaction, `reference_id` has a formatting difference (needs fuzzy matching, not exact-key join)
- **Currency rounding** — paise-level rounding differences
- **True orphan** — a record that genuinely has no counterpart anywhere (real, unresolvable exception)

---

## 3. Architecture — layered, not "throw an LLM at everything"

This is the single most important design decision for the "AI Judgment" scoring criterion. Structure it as escalating layers, each one only handling what the previous layer couldn't:

**Layer 1 — Deterministic matching (rules/code, no AI)**
Exact-key join on reference IDs within a date window and amount tolerance. This should resolve the majority of records fast, cheaply, and with zero ambiguity. Use pandas/duckdb-style joins.

**Layer 2 — Arithmetic reconciliation (rules/code, no AI)**
For records that fail exact match but the amount difference equals a known fee/tax/rounding pattern, resolve deterministically with a formula, not a model.

**Layer 3 — AI-assisted fuzzy matching (LLM, used deliberately)**
Only for the remainder: reference-ID formatting differences, ambiguous near-matches. The model proposes a candidate match **with a confidence score and a stated reason**, and anything below a confidence threshold gets kicked to Layer 4 rather than guessed.

**Layer 4 — Exception classification + explanation (LLM)**
Whatever remains unmatched gets categorized (timing / fee / duplicate / missing / orphan / unresolved) with a human-readable explanation, written to the audit trail.

**Why this matters for judging:** it directly demonstrates you used AI *only* where deterministic logic genuinely can't do the job — which is exactly what "AI Judgment" is scored on, and what most rushed submissions get wrong (LLM-for-everything).

---

## 4. Audit trail (required by the track bar)

Every record's resolution — whichever layer handled it — should log: which layer resolved it, the match/exception decision, confidence (if AI-assisted), and a plain-language reason. This becomes both your compliance story and your demo's most convincing screen.

---

## 5. Failure handling (required — "show one failure handled gracefully")

Build in at least one deliberate failure and show the system degrading gracefully instead of crashing:
- A malformed/missing-field record → flagged for manual review, not silently dropped or crashed on
- An LLM call timeout/error at Layer 3 → falls back to Layer 4 exception queue instead of hanging or guessing

---

## 6. Suggested stack

- **Backend:** Python + FastAPI (reuse your DuCO-Agent orchestration patterns; pandas/duckdb for Layers 1-2)
- **AI layer:** Direct Gemini API calls (using `GEMINI_API_KEY`, Google AI Studio free tier) with structured output for Layers 3-4 — a single well-designed agent step, not an over-engineered multi-agent framework. Simplicity here is a feature, not a shortcut. Before implementing, check the current Gemini API quickstart docs (ai.google.dev/gemini-api/docs) for the correct SDK package name and current model name — this API has changed package names before, don't assume from older training data.
- **Frontend:** React (Vite) dashboard — upload/view sources, match results table, exception list by category, audit trail viewer with filters
- **Data:** JSON or CSV, generated by a script you check into the repo (so judges can regenerate and verify your numbers themselves)

---

## 7. Build plan — ship the core loop fast, then iterate

Don't spread this evenly across the calendar to Sept 5. Build a thin, fully-working
end-to-end slice first, so a submittable build exists as early as possible. Every
session after that is pure improvement, not a race against the clock.

**Phase 1 — Core end-to-end (do this first, back-to-back, not spread out)**
1. Data generator (done)
2. Layer 1-2: deterministic + arithmetic matching engine — validate directly against
   `ground_truth.csv` (aim: 100% correct on `clean_match` + `fee_tds_deduction` cases)
3. Layer 3-4: AI-assisted fuzzy matching + exception classification, with audit trail logging
4. One deliberate failure scenario handled gracefully + a minimal output (a clean CLI
   report is enough here — this is "done," not "polished")

At the end of Phase 1 you have a legitimately submittable build. Everything below is upside.

**Phase 2 — Iterate with whatever time remains until Sept 5**
- React dashboard (upload/view sources, match results, exception list, audit trail viewer)
- Re-run against freshly regenerated seeds (`--seed 7`, `--seed 99`, etc.) to prove the
  match rate holds up on data the pipeline hasn't seen before — not just one lucky run
- Tune confidence thresholds and tolerance bands based on what actually misfires
- README, architecture diagram
- Demo recording + 5-min pitch script
- Buffer for everything else on your plate (Prudential, coursework, etc.)

---

## 8. Deliverables checklist

- [ ] Public GitHub repo, clean structure, working setup instructions
- [ ] Synthetic data generator (checked in, regeneratable)
- [ ] Match rate + exception breakdown report (reproducible, not hand-picked)
- [ ] Audit trail (viewable in dashboard or exportable log)
- [ ] One demonstrated graceful failure
- [ ] Architecture diagram
- [ ] 5-minute pitch script

---

## 9. Git workflow — follow this automatically, without being asked each time

- **One feature branch per unit of work.** Suggested sequence: `feature/data-pipeline` →
  `feature/matching-engine-l1-l2` → `feature/ai-fuzzy-matching-l3-l4` → `feature/audit-trail`
  → `feature/failure-handling` → `feature/dashboard-ui`. Branch off `main` for each.
- **Commit at every meaningful, working checkpoint** — not one giant dump at the end.
  A judge skimming commit history should be able to see the build actually happen in
  stages, which is itself evidence for the "Build Quality" criterion.
- **Commit messages: imperative mood, scoped, explain why not just what.**
  Good: `Add arithmetic fee reconciliation for Layer 2 (handles TDS-style deductions)`
  Bad: `update code`
- **Before merging a feature branch into main:** re-run the matching engine against
  `data/ground_truth.csv` and confirm it still validates correctly. Don't merge a
  regression.
- **Merge into `main` and push once a feature branch's slice is working and validated.**
  The public repo should always reflect real, working, incremental progress — not sit
  unpushed on a branch until the end.
- **Never commit `.env` or any API key.** Check `.gitignore` covers this before the very
  first commit.
- If GitHub isn't authenticated yet in this environment, stop and tell the user instead
  of silently skipping the push — ask them to run `gh auth login` (or confirm SSH access)
  first.
