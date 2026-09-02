import { useEffect, useState } from "react";
import "./App.css";
import { api } from "./api";
import SummaryPanel from "./components/SummaryPanel";
import SourcesView from "./components/SourcesView";
import ExceptionList from "./components/ExceptionList";
import AuditTrailTable from "./components/AuditTrailTable";

const TABS = ["Summary", "Sources", "Exceptions", "Audit Trail"];

function App() {
  const [tab, setTab] = useState("Summary");
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  const [rerunning, setRerunning] = useState(false);

  const loadSummary = () => api.summary().then(setSummary).catch((err) => setError(err.message));

  useEffect(() => {
    loadSummary();
  }, []);

  const handleRerun = async (fn) => {
    setRerunning(true);
    setError(null);
    try {
      await fn();
      await loadSummary();
    } catch (err) {
      setError(err.message);
    } finally {
      setRerunning(false);
    }
  };

  return (
    <div className="app">
      <header>
        <h1>Payment Reconciliation Agent</h1>
        <p className="subtitle">Gateway log &harr; bank settlement &harr; merchant ledger, reconciled across four escalating layers.</p>
      </header>

      {error && <p className="error banner-error">{error}</p>}

      <nav className="tabs">
        {TABS.map((t) => (
          <button key={t} className={t === tab ? "active" : ""} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </nav>

      <main>
        {tab === "Summary" && (
          <SummaryPanel
            summary={summary}
            rerunning={rerunning}
            onRerunLayer12={() => handleRerun(api.rerunLayer12)}
            onRerunFull={() => handleRerun(api.rerunFull)}
          />
        )}
        {tab === "Sources" && <SourcesView />}
        {tab === "Exceptions" && <ExceptionList />}
        {tab === "Audit Trail" && summary && (
          <AuditTrailTable availableCategories={Object.keys(summary.category_breakdown)} />
        )}
      </main>
    </div>
  );
}

export default App;
