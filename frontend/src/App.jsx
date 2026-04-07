import { useState } from "react";
import Dashboard from "./pages/Dashboard";
import BatchMonitor from "./pages/BatchMonitor";
import Failures from "./pages/Failures";

const globalStyle = `
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #11111b; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
`;

export default function App() {
  const [page, setPage] = useState("dashboard");
  const [activeBatchId, setActiveBatchId] = useState(null);

  function handleStartBatch(batchId) {
    setActiveBatchId(batchId);
    setPage("batch");
  }

  function handleViewBatch(batchId) {
    setActiveBatchId(batchId);
    setPage("batch");
  }

  return (
    <>
      <style>{globalStyle}</style>

      {/* Nav */}
      <nav style={{
        background: "#1e1e2e",
        borderBottom: "1px solid #313244",
        padding: "0 24px",
        display: "flex",
        alignItems: "center",
        gap: "4px",
        height: "52px",
      }}>
        <span style={{ color: "#cdd6f4", fontWeight: "700", marginRight: "16px", fontSize: "16px" }}>
          🧪 Physis Tester
        </span>
        {[
          { id: "dashboard", label: "Dashboard" },
          { id: "failures", label: "Failures" },
        ].map(n => (
          <button
            key={n.id}
            onClick={() => setPage(n.id)}
            style={{
              background: "transparent",
              border: "none",
              color: page === n.id ? "#89b4fa" : "#6c7086",
              borderBottom: page === n.id ? "2px solid #89b4fa" : "2px solid transparent",
              padding: "0 12px",
              height: "52px",
              cursor: "pointer",
              fontSize: "14px",
              fontWeight: page === n.id ? "600" : "400",
            }}
          >
            {n.label}
          </button>
        ))}
      </nav>

      {/* Pages */}
      {page === "dashboard" && (
        <Dashboard onStartBatch={handleStartBatch} onViewBatch={handleViewBatch} />
      )}
      {page === "batch" && activeBatchId && (
        <BatchMonitor batchId={activeBatchId} onBack={() => setPage("dashboard")} />
      )}
      {page === "failures" && (
        <Failures onBack={() => setPage("dashboard")} />
      )}
    </>
  );
}
