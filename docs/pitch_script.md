# 5-Minute Pitch Script

## 0:00 - 0:45 -- The problem

"A merchant's money moves through three systems that are supposed to agree
and almost never do cleanly: what the payment gateway logged, what actually
landed in the bank net of fees, and what the merchant's own ledger recorded
as revenue. Someone on a finance-ops team reconciles this by hand every
month -- cross-referencing spreadsheets, chasing down why a number is off by
exactly the gateway fee, or by a refund, or by nothing explainable at all.

That's what this agent automates: it matches records across all three
sources, reports a match rate, and -- this is the part that matters --
produces an honest, categorized list of the exceptions it *couldn't* resolve,
with a plain-language reason for each one. Not 'these don't match.' Why."

## 0:45 - 2:00 -- Architecture: AI only where it earns its place

"The obvious wrong way to build this is to hand every record to an LLM and
ask 'does this match?' That's slow, expensive, and it's not auditable -- you
can't explain to a compliance reviewer why the model said yes.

So this is four escalating layers, and each one only ever sees what the
layer before it explicitly couldn't resolve.

Layer 1 is a plain exact-key join -- no AI. Layer 2 is arithmetic: does the
settlement amount equal amount minus fee minus tax, within a rounding
tolerance? Also no AI. Between them, these two layers resolve the large
majority of records with zero ambiguity, and validate at 100% against a
held-out ground truth on the categories that are supposed to be
deterministic.

[SHOW: dashboard Summary tab -- point at match rate and category chips]

What's left after Layer 1-2 is the genuinely hard stuff: a ledger reference
that's a cosmetically mangled version of a real payment ID, or a settlement
that's short by an amount no formula explains. That's Layer 3 -- and even
there, before it calls the model at all, it prefilters candidates by amount.
If nothing matches on amount, there's nothing to propose, so it skips the
API call entirely. On this dataset, that cuts ~70 records down to about 6-7
real model calls. The model returns a match decision *with a confidence
score and a stated reason* -- and anything below threshold doesn't get
forced through, it gets kicked to Layer 4 instead of guessed at.

Layer 4 is exception classification and explanation -- it takes what's left,
confirms or refines the category, and writes the plain-language reason that
ends up in the audit trail."

## 2:00 - 3:00 -- Demo: the dashboard

[SHOW: Sources tab -- "here are the three raw sources, exactly as checked into
the repo, regeneratable with a one-line script and a seed"]

[SHOW: Exceptions tab -- click into 'True orphan' and 'Needs fuzzy match']

"Here's a fuzzy match Layer 3 actually resolved: ledger reference `pay-
fZTvvWGvgSCecS` against gateway payment `pay_fZTvvWGvgSCecS` -- confidence
0.95, reason stated inline. And here's a true orphan Layer 4 correctly
classified even though Layer 3 couldn't find a candidate for it -- an
entry with no gateway counterpart anywhere in the dataset."

[SHOW: Audit Trail tab -- filter by layer = 3, then layer = 4]

"Every one of these seventy-odd records has exactly one row here: which
layer touched it, its confidence, and why. That's the compliance story."

## 3:00 - 3:45 -- Failure handling: the part everyone skips

"Two failure modes are built in on purpose, not simulated for the demo.

One: a malformed record -- missing ID, non-numeric amount, whatever --
gets flagged for manual review at load time. It doesn't crash the pipeline
and it doesn't silently vanish.

Two: an LLM error or timeout at Layer 3 or 4. This is not hypothetical --
we hit it for real, live, against the Gemini free tier's rate limit during
development. Every single failed call fell back to the next layer with a
clear note in the audit trail instead of hanging or making something up.
That's not a mocked test path. That happened."

## 3:45 - 4:30 -- Proving the numbers aren't cherry-picked

"The match-rate number is only worth anything if it's not tuned to one lucky
dataset. The generator is checked into the repo with a seed -- anyone can
regenerate it and get the same categories. We re-ran the same pipeline
against two more seeds it had never seen, and the accuracy held: 98.4%,
96.8%, both with the required gate categories at 100%. Same one edge case
missed both times, for the same understood reason -- not a new failure
mode showing up on fresh data."

## 4:30 - 5:00 -- Impact and close

"Here's the business case in one number: Layer 1-2 runs at 0.2 milliseconds
per record -- benchmarked, not estimated. A mid-market merchant processing
5,000 transactions a month: that's 1.2 seconds of compute, replacing roughly
250 analyst-hours of manual cross-referencing. What remains is a few minutes
of exception review on the records the engine honestly couldn't resolve.

That's the design: not AI doing everything, just AI doing the part no
formula can -- and the rest handled deterministically, cheaply, and in a way
a compliance reviewer can actually audit.

At scale, this sits naturally inside a payment gateway console. Razorpay
already has the three data sources -- gateway log, settlement file, merchant
ledger. The reconciliation layer is the missing piece."

---

## Timing notes

- Keep the demo clicks pre-loaded (dashboard already running against a
  populated audit trail) -- don't demo a live Layer 3-4 rerun on stage, the
  free-tier rate limit makes it take several minutes.
- If asked "why Gemini and not Claude": the build brief was updated
  mid-build to specify Gemini's free tier; the AI layer is provider-swappable
  by design (`ai_client.call_tool` is the only integration point).
