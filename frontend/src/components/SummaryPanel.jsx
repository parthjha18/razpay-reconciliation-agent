const CATEGORY_LABELS = {
  matched_layer1_2: "Matched (Layer 1-2)",
  matched_extended_window: "Matched, late settlement",
  matched_layer3: "Matched (Layer 3, AI)",
  exception_fee_mismatch: "Fee/TDS mismatch",
  exception_refund_mismatch: "Refund mismatch",
  exception_duplicate: "Duplicate entry",
  exception_pending_settlement: "Pending settlement",
  exception_rounding: "Currency rounding",
  true_exception_orphan: "True orphan",
  exception_needs_fuzzy_match: "Needs fuzzy match (Layer 3/4)",
  exception_unclassified: "Unclassified",
  exception_manual_review: "Manual review",
};

const MATCHED_CATEGORIES = new Set([
  "matched_layer1_2",
  "matched_extended_window",
  "matched_layer3",
]);

export function categoryLabel(category) {
  return CATEGORY_LABELS[category] || category;
}

export default function SummaryPanel({ summary, onRerunLayer12, onRerunFull, rerunning }) {
  if (!summary) return null;

  const matchedCount = Object.entries(summary.category_breakdown)
    .filter(([category]) => MATCHED_CATEGORIES.has(category))
    .reduce((sum, [, count]) => sum + count, 0);
  const exceptionCount = summary.total_records - matchedCount;

  return (
    <div className="summary-panel">
      <div className="summary-cards">
        <div className="card">
          <div className="card-value">{summary.total_records}</div>
          <div className="card-label">Total records</div>
        </div>
        <div className="card card-good">
          <div className="card-value">{(summary.match_rate * 100).toFixed(1)}%</div>
          <div className="card-label">Match rate</div>
        </div>
        <div className="card">
          <div className="card-value">{matchedCount}</div>
          <div className="card-label">Matched</div>
        </div>
        <div className="card card-warn">
          <div className="card-value">{exceptionCount}</div>
          <div className="card-label">Exceptions</div>
        </div>
      </div>

      <div className="category-breakdown">
        {Object.entries(summary.category_breakdown).map(([category, count]) => (
          <div key={category} className={`chip ${MATCHED_CATEGORIES.has(category) ? "chip-good" : "chip-warn"}`}>
            {categoryLabel(category)}: {count}
          </div>
        ))}
      </div>

      <div className="rerun-actions">
        <button onClick={onRerunLayer12} disabled={rerunning}>
          Re-run Layer 1-2 (fast, free)
        </button>
        <button onClick={onRerunFull} disabled={rerunning} className="primary">
          Re-run full pipeline (Layers 1-4, calls Gemini)
        </button>
        {rerunning && <span className="rerun-status">Running... this can take a few minutes on the free API tier.</span>}
      </div>
      <p className="source-note">Showing: {summary.source}</p>
    </div>
  );
}
