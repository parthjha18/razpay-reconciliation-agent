import { useEffect, useState } from "react";
import { api } from "../api";
import { categoryLabel } from "./SummaryPanel";

const RECORD_TYPES = ["gateway_payment", "settlement_orphan", "ledger_orphan", "fuzzy_matched_transaction"];

export default function AuditTrailTable({ availableCategories }) {
  const [rows, setRows] = useState([]);
  const [filters, setFilters] = useState({ category: "", record_type: "", layer: "" });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    api
      .auditTrail(filters)
      .then((data) => setRows(data.rows))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [filters]);

  return (
    <div>
      <div className="filters">
        <select value={filters.category} onChange={(e) => setFilters({ ...filters, category: e.target.value })}>
          <option value="">All categories</option>
          {availableCategories.map((c) => (
            <option key={c} value={c}>
              {categoryLabel(c)}
            </option>
          ))}
        </select>
        <select value={filters.record_type} onChange={(e) => setFilters({ ...filters, record_type: e.target.value })}>
          <option value="">All record types</option>
          {RECORD_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select value={filters.layer} onChange={(e) => setFilters({ ...filters, layer: e.target.value })}>
          <option value="">All layers</option>
          {[1, 2, 3, 4].map((l) => (
            <option key={l} value={l}>
              Layer {l}
            </option>
          ))}
        </select>
      </div>

      {error && <p className="error">{error}</p>}
      {loading ? (
        <p>Loading...</p>
      ) : (
        <table className="audit-table">
          <thead>
            <tr>
              <th>Key</th>
              <th>Layer</th>
              <th>Category</th>
              <th>Confidence</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                <td className="key-cell">{row.order_id || row.payment_id || row.utr || row.invoice_id}</td>
                <td>{row.layer}</td>
                <td>
                  <span className={`tag ${row.category.startsWith("matched") ? "tag-good" : "tag-warn"}`}>
                    {categoryLabel(row.category)}
                  </span>
                </td>
                <td>{row.confidence != null ? row.confidence.toFixed(2) : "-"}</td>
                <td className="reason-cell">{row.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {!loading && rows.length === 0 && !error && <p>No records match these filters.</p>}
    </div>
  );
}
