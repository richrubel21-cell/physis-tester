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

export default function Dashboard({ onStartBatch, onViewBatch, onViewMaryBatch }) {
  const [summary,      setSummary]      = useState(null);
  const [batches,      setBatches]      = useState([]);
  const [maryBatches,  setMaryBatches]  = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [starting,     setStarting]     = useState(false);
  const [startingMary, setStartingMary] = useState(false);
  const [count,        setCount]        = useState(10);
  const [useAi,        setUseAi]        = useState(true);
  const [maryCount,    setMaryCount]    = useState(10);
  const [maryUseAi,    setMaryUseAi]    = useState(true);

  useEffect(() => { loadData(); }, []);

  async function loadData() {
    try {
      const [s, b, mb] = await Promise.all([
        api.getSummary(),
        api.listBatches(),
        api.listMaryBatches(),
      ]);
      setSummary(s);
      setBatches(b.batches || []);
      setMaryBatches(mb.batches || []);
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

  async function handleStartMaryBatch() {
    setStartingMary(true);
    try {
      const result = await api.startMaryBatch(maryCount, maryUseAi);
      onViewMaryBatch(result.batch_id);
    } catch (e) {
      alert("Failed to start Mary batch: " + (e.response?.data?.detail || e.message));
    } finally {
      setStartingMary(false);
    }
  }

  const passColor = (rate) => {
    if (rate >= 80) return "#a6e3a1";
    if (rate >= 50) return "#f9e2af";
    return "#f38ba8";
  };

  return (
    <div style={{ maxWidth: "1100px", margin: "0 auto", padding: "32px 16px" }}>
      <h1 style={{ color: "#cdd6f4", fontSize: "28px", marginBottom: "8px" }}>🧪 Physis Tester</h1>
      <p style={{ color: "#6c7086", marginBottom: "32px" }}>Simulated human testing for the Physis AI factory</p>

      {/* Stats */}
      {summary && (
        <div style={{ display: "flex", gap: "12px", marginBottom: "24px", flexWrap: "wrap" }}>
          <div style={statBox}>
            <div style={{ fontSize: "32px", fontWeight: "700", color: "#cdd6f4" }}>{summary.total_runs}</div>
            <div style={{ color: "#6c7086", fontSize: "13px", marginTop: "4px" }}>Total Runs</div>
          </div>
          <div style={statBox}>
            <div style={{ fontSize: "32px", fontWeight: "700", color: passColor(summary.pass_rate_percent) }}>{summary.pass_rate_percent}%</div>
            <div style={{ color: "#6c7086", fontSize: "13px", marginTop: "4px" }}>Pass Rate</div>
          </div>
          <div style={statBox}>
            <div style={{ fontSize: "32px", fontWeight: "700", color: "#89b4fa" }}>{summary.avg_build_time_seconds ?? "—"}s</div>
            <div style={{ color: "#6c7086", fontSize: "13px", marginTop: "4px" }}>Avg Build Time</div>
          </div>
          <div style={statBox}>
            <div style={{ fontSize: "32px", fontWeight: "700", color: "#f38ba8" }}>{summary.failed + summary.errors}</div>
            <div style={{ color: "#6c7086", fontSize: "13px", marginTop: "4px" }}>Failures</div>
          </div>
        </div>
      )}

      {/* Two-column starters */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>

        {/* Build Batch */}
        <div style={card}>
          <h2 style={{ color: "#cdd6f4", fontSize: "18px", marginBottom: "16px" }}>▶ Start Build Batch</h2>
          <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
            <div>
              <label style={{ color: "#6c7086", fontSize: "13px", display: "block", marginBottom: "6px" }}>Scenario Count</label>
              <input type="number" min={1} max={50} value={count}
                onChange={e => setCount(Number(e.target.value))}
                style={{ background: "#181825", border: "1px solid #313244", borderRadius: "8px", color: "#cdd6f4", padding: "8px 12px", width: "80px", fontSize: "15px" }} />
            </div>
            <div>
              <label style={{ color: "#6c7086", fontSize: "13px", display: "block", marginBottom: "6px" }}>AI Variation</label>
              <button onClick={() => setUseAi(!useAi)}
                style={{ background: useAi ? "#313244" : "#181825", border: `1px solid ${useAi ? "#89b4fa" : "#313244"}`, borderRadius: "8px", color: useAi ? "#89b4fa" : "#6c7086", padding: "8px 16px", cursor: "pointer", fontSize: "14px" }}>
                {useAi ? "✓ Enabled" : "Disabled"}
              </button>
            </div>
            <div style={{ marginTop: "18px" }}>
              <button onClick={handleStartBatch} disabled={starting}
                style={{ background: starting ? "#313244" : "#89b4fa", border: "none", borderRadius: "8px", color: starting ? "#6c7086" : "#1e1e2e", padding: "10px 24px", cursor: starting ? "not-allowed" : "pointer", fontWeight: "700", fontSize: "15px" }}>
                {starting ? "Starting..." : "Run Batch"}
              </button>
            </div>
          </div>
          <p style={{ color: "#6c7086", fontSize: "12px", marginTop: "12px" }}>
            Generates AI scenarios and runs full end-to-end Physis builds.
          </p>
        </div>

        {/* Mary Batch */}
        <div style={{ ...card, border: "1px solid #44385a" }}>
          <h2 style={{ color: "#c4b5fd", fontSize: "18px", marginBottom: "16px" }}>🦋 Test Mary</h2>
          <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
            <div>
              <label style={{ color: "#6c7086", fontSize: "13px", display: "block", marginBottom: "6px" }}>Prompt Count</label>
              <input type="number" min={1} max={50} value={maryCount}
                onChange={e => setMaryCount(Number(e.target.value))}
                style={{ background: "#181825", border: "1px solid #313244", borderRadius: "8px", color: "#cdd6f4", padding: "8px 12px", width: "80px", fontSize: "15px" }} />
            </div>
            <div>
              <label style={{ color: "#6c7086", fontSize: "13px", display: "block", marginBottom: "6px" }}>AI Variation</label>
              <button onClick={() => setMaryUseAi(!maryUseAi)}
                style={{ background: maryUseAi ? "#2a1e3a" : "#181825", border: `1px solid ${maryUseAi ? "#7c3aed" : "#313244"}`, borderRadius: "8px", color: maryUseAi ? "#c4b5fd" : "#6c7086", padding: "8px 16px", cursor: "pointer", fontSize: "14px" }}>
                {maryUseAi ? "✓ Enabled" : "Disabled"}
              </button>
            </div>
            <div style={{ marginTop: "18px" }}>
              <button onClick={handleStartMaryBatch} disabled={startingMary}
                style={{ background: startingMary ? "#313244" : "#7c3aed", border: "none", borderRadius: "8px", color: startingMary ? "#6c7086" : "white", padding: "10px 24px", cursor: startingMary ? "not-allowed" : "pointer", fontWeight: "700", fontSize: "15px" }}>
                {startingMary ? "Starting..." : "🦋 Test Mary"}
              </button>
            </div>
          </div>
          <p style={{ color: "#6c7086", fontSize: "12px", marginTop: "12px" }}>
            Generates AI-varied user prompts across all 5 screens. Scores on 7 criteria: context, tone, helpfulness, speakability, length, persona, and responsiveness.
          </p>
        </div>
      </div>

      {/* Two-column history */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", marginTop: "16px" }}>

        {/* Build Batch History */}
        <div style={card}>
          <h2 style={{ color: "#cdd6f4", fontSize: "18px", marginBottom: "16px" }}>📋 Recent Build Batches</h2>
          {loading ? (
            <p style={{ color: "#6c7086" }}>Loading...</p>
          ) : batches.length === 0 ? (
            <p style={{ color: "#6c7086" }}>No build batches yet.</p>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #313244" }}>
                  {["ID", "Status", "Pass Rate", "Runs", "Started"].map(h => (
                    <th key={h} style={{ color: "#6c7086", fontSize: "12px", textAlign: "left", padding: "8px 0", fontWeight: "600" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {batches.map(b => {
                  const rate = b.total > 0 ? Math.round(b.passed / b.total * 100) : 0;
                  return (
                    <tr key={b.batch_id} onClick={() => onViewBatch(b.batch_id)}
                      style={{ borderBottom: "1px solid #181825", cursor: "pointer" }}
                      onMouseEnter={e => { e.currentTarget.style.background = "#181825"; }}
                      onMouseLeave={e => { e.currentTarget.style.background = "transparent"; }}>
                      <td style={{ color: "#89b4fa", padding: "10px 0", fontSize: "14px" }}>#{b.batch_id}</td>
                      <td style={{ padding: "10px 0" }}>
                        <span style={{ background: b.status === "completed" ? "#1e3a2e" : b.status === "running" ? "#1e2a3a" : "#2a1e1e", color: b.status === "completed" ? "#a6e3a1" : b.status === "running" ? "#89b4fa" : "#f38ba8", borderRadius: "6px", padding: "2px 10px", fontSize: "12px", fontWeight: "600" }}>
                          {b.status}
                        </span>
                      </td>
                      <td style={{ color: passColor(rate), padding: "10px 0", fontSize: "14px" }}>{rate}%</td>
                      <td style={{ color: "#cdd6f4", padding: "10px 0", fontSize: "14px" }}>{b.completed}/{b.total}</td>
                      <td style={{ color: "#6c7086", padding: "10px 0", fontSize: "13px" }}>{new Date(b.started_at).toLocaleString()}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Mary Batch History */}
        <div style={{ ...card, border: "1px solid #44385a" }}>
          <h2 style={{ color: "#c4b5fd", fontSize: "18px", marginBottom: "16px" }}>🦋 Recent Mary Batches</h2>
          {loading ? (
            <p style={{ color: "#6c7086" }}>Loading...</p>
          ) : maryBatches.length === 0 ? (
            <p style={{ color: "#6c7086" }}>No Mary batches yet.</p>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #313244" }}>
                  {["ID", "Status", "Pass Rate", "Prompts", "Started"].map(h => (
                    <th key={h} style={{ color: "#6c7086", fontSize: "12px", textAlign: "left", padding: "8px 0", fontWeight: "600" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {maryBatches.map(b => (
                  <tr key={b.batch_id} onClick={() => onViewMaryBatch(b.batch_id)}
                    style={{ borderBottom: "1px solid #181825", cursor: "pointer" }}
                    onMouseEnter={e => { e.currentTarget.style.background = "#181825"; }}
                    onMouseLeave={e => { e.currentTarget.style.background = "transparent"; }}>
                    <td style={{ color: "#c4b5fd", padding: "10px 0", fontSize: "14px" }}>#{b.batch_id}</td>
                    <td style={{ padding: "10px 0" }}>
                      <span style={{ background: b.status === "completed" ? "#1e3a2e" : b.status === "running" ? "#1e2a3a" : "#2a1e1e", color: b.status === "completed" ? "#a6e3a1" : b.status === "running" ? "#89b4fa" : "#f38ba8", borderRadius: "6px", padding: "2px 10px", fontSize: "12px", fontWeight: "600" }}>
                        {b.status}
                      </span>
                    </td>
                    <td style={{ color: passColor(b.pass_rate ?? 0), padding: "10px 0", fontSize: "14px" }}>{b.pass_rate ?? 0}%</td>
                    <td style={{ color: "#cdd6f4", padding: "10px 0", fontSize: "14px" }}>{b.completed}/{b.total}</td>
                    <td style={{ color: "#6c7086", padding: "10px 0", fontSize: "13px" }}>{new Date(b.started_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
