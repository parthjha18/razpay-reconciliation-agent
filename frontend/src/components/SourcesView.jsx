import { useEffect, useState } from "react";
import { api } from "../api";

function SourceTable({ title, rows }) {
  if (!rows || rows.length === 0) return null;
  const columns = Object.keys(rows[0]);
  return (
    <div className="source-table-wrapper">
      <h3>
        {title} <span className="count-badge">{rows.length}</span>
      </h3>
      <div className="table-scroll">
        <table className="audit-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {columns.map((col) => (
                  <td key={col}>{String(row[col])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function SourcesView() {
  const [sources, setSources] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.sources().then(setSources).catch((err) => setError(err.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!sources) return <p>Loading...</p>;

  return (
    <div className="sources-view">
      <SourceTable title="Payment Gateway Log" rows={sources.gateway} />
      <SourceTable title="Bank Settlement File" rows={sources.settlement} />
      <SourceTable title="Merchant Ledger" rows={sources.ledger} />
    </div>
  );
}
