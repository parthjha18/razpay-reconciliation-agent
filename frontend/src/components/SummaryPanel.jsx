const CATEGORY_LABELS = {
  matched_layer1_2: "Matched (Layer 1-2)",
  matched_extended_window: "Matched, late settlement",
  matched_layer3: "Matched (Layer 3, AI)",
  exception_fee_mismatch: "Fee / TDS mismatch",
  exception_refund_mismatch: "Refund mismatch",
  exception_duplicate: "Duplicate entry",
  exception_pending_settlement: "Pending settlement",
  exception_rounding: "Currency rounding",
  true_exception_orphan: "True orphan",
  exception_needs_fuzzy_match: "Needs fuzzy match",
  exception_unclassified: "Unclassified",
  exception_manual_review: "Manual review",
};

const CATEGORY_COLORS = {
  matched_layer1_2:           "#2f9e44",
  matched_extended_window:    "#40c057",
  matched_layer3:             "#0c9e7a",
  exception_pending_settlement: "#f08c00",
  exception_rounding:         "#f59f00",
  exception_fee_mismatch:     "#e8590c",
  exception_refund_mismatch:  "#d9480f",
  exception_duplicate:        "#c92a2a",
  true_exception_orphan:      "#a61e4d",
  exception_needs_fuzzy_match:"#7950f2",
  exception_unclassified:     "#868e96",
  exception_manual_review:    "#868e96",
};

const MATCHED_CATEGORIES = new Set([
  "matched_layer1_2",
  "matched_extended_window",
  "matched_layer3",
]);

export function categoryLabel(cat) {
  return CATEGORY_LABELS[cat] || cat;
}

export function categoryColor(cat) {
  return CATEGORY_COLORS[cat] || "#868e96";
}

function DonutChart({ matched, total }) {
  const r = 58;
  const cx = 80;
  const cy = 80;
  const circ = 2 * Math.PI * r;
  const matchedArc = circ * (matched / total);
  const pct = ((matched / total) * 100).toFixed(1);

  return (
    <svg viewBox="0 0 160 160" width="160" height="160" aria-label={`Match rate ${pct}%`}>
      {/* track */}
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--border)" strokeWidth="18" />
      {/* exceptions arc */}
      <circle
        cx={cx} cy={cy} r={r} fill="none"
        stroke="rgba(232,89,12,0.55)" strokeWidth="18"
        strokeDasharray={`${circ - matchedArc} ${circ}`}
        strokeDashoffset={-matchedArc}
        transform={`rotate(-90 ${cx} ${cy})`}
      />
      {/* matched arc */}
      <circle
        cx={cx} cy={cy} r={r} fill="none"
        stroke="#2f9e44" strokeWidth="18"
        strokeDasharray={`${matchedArc} ${circ}`}
        transform={`rotate(-90 ${cx} ${cy})`}
      />
      <text x={cx} y={cy - 8} textAnchor="middle" fontSize="22" fontWeight="700" fill="var(--text-h)">{pct}%</text>
      <text x={cx} y={cy + 10} textAnchor="middle" fontSize="11" fill="var(--text)">match rate</text>
    </svg>
  );
}

function CategoryBars({ breakdown, total }) {
  const sorted = Object.entries(breakdown).sort((a, b) => b[1] - a[1]);
  return (
    <div className="cat-bars">
      {sorted.map(([cat, count]) => {
        const pct = (count / total) * 100;
        const color = categoryColor(cat);
        return (
          <div key={cat} className="cat-bar-row">
            <div className="cat-bar-label" style={{ color }}>
              {categoryLabel(cat)}
            </div>
            <div className="cat-bar-track">
              <div className="cat-bar-fill" style={{ width: `${pct}%`, background: color }} />
            </div>
            <div className="cat-bar-count">{count}</div>
          </div>
        );
      })}
    </div>
  );
}

export default function SummaryPanel({ summary, onRerunLayer12, onRerunFull, rerunning }) {
  if (!summary) return null;

  const matchedCount = Object.entries(summary.category_breakdown)
    .filter(([cat]) => MATCHED_CATEGORIES.has(cat))
    .reduce((sum, [, n]) => sum + n, 0);
  const exceptionCount = summary.total_records - matchedCount;

  return (
    <div className="summary-panel">
      {/* Hero row */}
      <div className="summary-hero">
        <DonutChart matched={matchedCount} total={summary.total_records} />
        <div className="summary-stats">
          <div className="stat-card">
            <div className="stat-value">{summary.total_records}</div>
            <div className="stat-label">Total records</div>
          </div>
          <div className="stat-card stat-good">
            <div className="stat-value">{matchedCount}</div>
            <div className="stat-label">Matched</div>
          </div>
          <div className="stat-card stat-warn">
            <div className="stat-value">{exceptionCount}</div>
            <div className="stat-label">Exceptions</div>
          </div>
          <div className="stat-card">
            <div className="stat-value stat-mono">~0.2 ms</div>
            <div className="stat-label">Per record (L1-2)</div>
          </div>
        </div>
      </div>

      {/* Category breakdown */}
      <div className="section-heading">Category breakdown</div>
      <CategoryBars breakdown={summary.category_breakdown} total={summary.total_records} />

      {/* Legend */}
      <div className="legend-row">
        <span className="legend-dot" style={{ background: "#2f9e44" }} /> Matched
        <span className="legend-dot" style={{ background: "#e8590c", marginLeft: 14 }} /> Exception
        <span className="legend-dot" style={{ background: "#7950f2", marginLeft: 14 }} /> Needs fuzzy match
      </div>

      {/* Rerun actions */}
      <div className="rerun-actions">
        <button onClick={onRerunLayer12} disabled={rerunning}>
          Re-run Layer 1-2 (fast, free)
        </button>
        <button onClick={onRerunFull} disabled={rerunning} className="primary">
          Re-run full pipeline (Layers 1-4, calls Gemini)
        </button>
        {rerunning && (
          <span className="rerun-status">Running… this takes a few minutes on the free API tier.</span>
        )}
      </div>
      <p className="source-note">Source: {summary.source}</p>
    </div>
  );
}
