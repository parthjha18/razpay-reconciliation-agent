import { useEffect, useState } from "react";
import { api } from "../api";
import { categoryLabel, categoryColor } from "./SummaryPanel";

const MATCHED_CATEGORIES = new Set(["matched_layer1_2", "matched_extended_window", "matched_layer3"]);

export default function ExceptionList() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .auditTrail()
      .then((data) => setRows(data.rows.filter((r) => !MATCHED_CATEGORIES.has(r.category))))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p>Loading...</p>;
  if (error) return <p className="error">{error}</p>;

  const grouped = rows.reduce((acc, row) => {
    (acc[row.category] ||= []).push(row);
    return acc;
  }, {});

  return (
    <div className="exception-list">
      {Object.entries(grouped).map(([category, categoryRows]) => (
        <details key={category} open>
          <summary>
            <span style={{ color: categoryColor(category) }}>{categoryLabel(category)}</span>
            <span className="count-badge">{categoryRows.length}</span>
          </summary>
          <ul>
            {categoryRows.map((row, i) => (
              <li key={i}>
                <div className="exception-key">
                  {row.order_id || row.payment_id || row.utr || row.invoice_id}
                  {row.confidence != null && <span className="confidence-badge">conf {row.confidence.toFixed(2)}</span>}
                </div>
                <div className="exception-reason">{row.reason}</div>
              </li>
            ))}
          </ul>
        </details>
      ))}
      {rows.length === 0 && <p>No exceptions -- everything matched.</p>}
    </div>
  );
}
