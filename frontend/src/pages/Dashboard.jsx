import { useState, useEffect } from "react";
import { api } from "../api/services";

const card = {
  background: "#1e1e2e",
  border: "1px solid #313244",
  borderRadius: "12px",
  padding: "24px",
  marginBottom: "16px",
};

const statBox = {
  background: "#181825",
  border: "1px solid #313244",
  borderRadius: "10px",
  padding: "20px",
  textAlign: "center",
  flex: 1,
};

export default function Dashboard({ onStartBatch, onViewBatch }) {
  const [summary, setSummary] = useState(null);
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [count, setCount] = useState(10);
  const [useAi, setUseAi] = useState(true);

  useEffect(() => {
    loadData();
  }, []); // runs on every mount, so returning from BatchMonitor refreshes stats

  async function loadData() {
    try {
      const [s, b] = await Promise.all([api.getSummary(), api.listBatches()]);
      setSummary(s);
      setBatches(b.batches || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function handleStartBatch() {
    setStarting(true);
    try {
      const result = await api.startBatch(count, useAi);
      onStartBatch(result.batch_id);
    } catch (e) {
      alert("Failed to start batch: " + (e.response?.data?.detail || e.message));
    } finally {
      setStarting(false);
    }
  }

  const passColor = (rate) => {
    if (rate >= 80) return "#a6e3a1";
    if (rate >= 50) return "#f9e2af";
    return "#f38ba8";
  };

  return (
    <div style={{ maxWidth: "900px", margin: "0 auto", padding: "32px 16px" }}>
      <h1 style={{ color: "#cdd6f4", fontSize: "28px", marginBottom: "8px" }}>
        🧪 Physis Tester
      </h1>
      <p style={{ color: "#6c7086", marginBottom: "32px" }}>
        Simulated human testing for the Physis AI factory
      </p>

      {/* Stats */}
      {summary && (
        <div style={{ display: "flex", gap: "12px", marginBottom: "24px", flexWrap: "wrap" }}>
          <div style={statBox}>
            <div style={{ fontSize: "32px", fontWeight: "700", color: "#cdd6f4" }}>
              {summary.total_runs}
            </div>
            <div style={{ color: "#6c7086", fontSize: "13px", marginTop: "4px" }}>Total Runs</div>
          </div>
          <div style={statBox}>
            <div style={{ fontSize: "32px", fontWeight: "700", color: passColor(summary.pass_rate_percent) }}>
              {summary.pass_rate_percent}%
            </div>
            <div style={{ color: "#6c7086", fontSize: "13px", marginTop: "4px" }}>Pass Rate</div>
          </div>
          <div style={statBox}>
            <div style={{ fontSize: "32px", fontWeight: "700", color: "#89b4fa" }}>
              {summary.avg_build_time_seconds ?? "—"}s
            </div>
            <div style={{ color: "#6c7086", fontSize: "13px", marginTop: "4px" }}>Avg Build Time</div>
          </div>
          <div style={statBox}>
            <div style={{ fontSize: "32px", fontWeight: "700", color: "#f38ba8" }}>
              {summary.failed + summary.errors}
            </div>
            <div style={{ color: "#6c7086", fontSize: "13px", marginTop: "4px" }}>Failures</div>
          </div>
        </div>
      )}

      {/* Start Batch */}
      <div style={card}>
        <h2 style={{ color: "#cdd6f4", fontSize: "18px", marginBottom: "16px" }}>
          ▶ Start New Batch
        </h2>
        <div style={{ display: "flex", alignItems: "center", gap: "16px", flexWrap: "wrap" }}>
          <div>
            <label style={{ color: "#6c7086", fontSize: "13px", display: "block", marginBottom: "6px" }}>
              Scenario Count
            </label>
            <input
              type="number"
              min={1}
              max={50}
              value={count}
              onChange={e => setCount(Number(e.target.value))}
              style={{
                background: "#181825",
                border: "1px solid #313244",
                borderRadius: "8px",
                color: "#cdd6f4",
                padding: "8px 12px",
                width: "80px",
                fontSize: "15px",
              }}
            />
          </div>
          <div>
            <label style={{ color: "#6c7086", fontSize: "13px", display: "block", marginBottom: "6px" }}>
              AI Variation
            </label>
            <button
              onClick={() => setUseAi(!useAi)}
              style={{
                background: useAi ? "#313244" : "#181825",
                border: `1px solid ${useAi ? "#89b4fa" : "#313244"}`,
                borderRadius: "8px",
                color: useAi ? "#89b4fa" : "#6c7086",
                padding: "8px 16px",
                cursor: "pointer",
                fontSize: "14px",
              }}
            >
              {useAi ? "✓ Enabled" : "Disabled"}
            </button>
          </div>
          <div style={{ marginTop: "18px" }}>
            <button
              onClick={handleStartBatch}
              disabled={starting}
              style={{
                background: starting ? "#313244" : "#89b4fa",
                border: "none",
                borderRadius: "8px",
                color: starting ? "#6c7086" : "#1e1e2e",
                padding: "10px 24px",
                cursor: starting ? "not-allowed" : "pointer",
                fontWeight: "700",
                fontSize: "15px",
              }}
            >
              {starting ? "Starting..." : "Run Batch"}
            </button>
          </div>
        </div>
      </div>

      {/* Recent Batches */}
      <div style={card}>
        <h2 style={{ color: "#cdd6f4", fontSize: "18px", marginBottom: "16px" }}>
          📋 Recent Batches
        </h2>
        {loading ? (
          <p style={{ color: "#6c7086" }}>Loading...</p>
        ) : batches.length === 0 ? (
          <p style={{ color: "#6c7086" }}>No batches yet. Start one above.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #313244" }}>
                {["ID", "Status", "Pass Rate", "Runs", "Started"].map(h => (
                  <th key={h} style={{ color: "#6c7086", fontSize: "12px", textAlign: "left", padding: "8px 0", fontWeight: "600" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {batches.map(b => (
                <tr
                  key={b.batch_id}
                  onClick={() => onViewBatch(b.batch_id)}
                  style={{ borderBottom: "1px solid #181825", cursor: "pointer" }}
                  onMouseEnter={e => e.currentTarget.style.background = "#181825"}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                >
                  <td style={{ color: "#89b4fa", padding: "10px 0", fontSize: "14px" }}>#{b.batch_id}</td>
                  <td style={{ padding: "10px 0" }}>
                    <span style={{
                      background: b.status === "completed" ? "#1e3a2e" : b.status === "running" ? "#1e2a3a" : "#2a1e1e",
                      color: b.status === "completed" ? "#a6e3a1" : b.status === "running" ? "#89b4fa" : "#f38ba8",
                      borderRadius: "6px",
                      padding: "2px 10px",
                      fontSize: "12px",
                      fontWeight: "600",
                    }}>
                      {b.status}
                    </span>
                  </td>
                  <td style={{ color: passColor(b.total > 0 ? Math.round(b.passed / b.total * 100) : 0), padding: "10px 0", fontSize: "14px" }}>
                    {b.total > 0 ? Math.round(b.passed / b.total * 100) : 0}%
                  </td>
                  <td style={{ color: "#cdd6f4", padding: "10px 0", fontSize: "14px" }}>
                    {b.completed}/{b.total}
                  </td>
                  <td style={{ color: "#6c7086", padding: "10px 0", fontSize: "13px" }}>
                    {new Date(b.started_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
