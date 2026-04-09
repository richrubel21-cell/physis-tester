import { useState, useEffect } from "react";
import { api } from "../api/services";
import { usePoll } from "../hooks/usePoll";

const statusColor = {
  passed: "#a6e3a1",
  failed: "#f38ba8",
  error: "#fab387",
  running: "#89b4fa",
  pending: "#6c7086",
};

const statusBg = {
  passed: "#1e3a2e",
  failed: "#3a1e1e",
  error: "#3a2a1e",
  running: "#1e2a3a",
  pending: "#1e1e2e",
};

export default function BatchMonitor({ batchId, onBack }) {
  const [batch, setBatch] = useState(null);
  const [loading, setLoading] = useState(true);
  const [hasFetched, setHasFetched] = useState(false);

  // FIX: stop polling on any terminal state, not just when status is 'running'/'pending'
  // Previously: batch?.status === "running" || batch?.status === "pending"
  // Bug: backend sets final status to "completed" — which is neither, so polling never stopped
  const isRunning = batch
    ? !["completed", "failed", "cancelled"].includes(batch.status)
    : false;

  async function fetchBatch() {
    try {
      const data = await api.getBatch(batchId);
      setBatch(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
      setHasFetched(true);
    }
  }

  useEffect(() => { fetchBatch(); }, [batchId]);
  usePoll(fetchBatch, 2000, isRunning && hasFetched);

  if (loading) return (
    <div style={{ color: "#6c7086", padding: "48px", textAlign: "center" }}>
      Loading batch #{batchId}...
    </div>
  );

  if (!batch) return (
    <div style={{ color: "#f38ba8", padding: "48px", textAlign: "center" }}>
      Batch not found.
      <button onClick={onBack} style={backBtn}>← Back</button>
    </div>
  );

  const progressPct = batch.total > 0 ? Math.round((batch.completed / batch.total) * 100) : 0;
  const passRate = batch.completed > 0 ? Math.round((batch.passed / batch.completed) * 100) : 0;

  return (
    <div style={{ maxWidth: "960px", margin: "0 auto", padding: "32px 16px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "16px", marginBottom: "24px" }}>
        <button onClick={onBack} style={backBtn}>← Back</button>
        <h1 style={{ color: "#cdd6f4", fontSize: "22px", margin: 0 }}>
          Batch #{batchId}
          <span style={{
            marginLeft: "12px",
            fontSize: "13px",
            background: statusBg[batch.status] || "#1e1e2e",
            color: statusColor[batch.status] || "#cdd6f4",
            borderRadius: "6px",
            padding: "2px 10px",
            fontWeight: "600",
          }}>
            {batch.status}
          </span>
        </h1>
        {isRunning && (
          <span style={{ color: "#89b4fa", fontSize: "13px", animation: "pulse 1.5s infinite" }}>
            ● Live
          </span>
        )}
      </div>

      {/* Progress bar */}
      <div style={{ background: "#181825", borderRadius: "8px", height: "10px", marginBottom: "24px", overflow: "hidden" }}>
        <div style={{
          background: passRate >= 80 ? "#a6e3a1" : passRate >= 50 ? "#f9e2af" : "#f38ba8",
          width: `${progressPct}%`,
          height: "100%",
          transition: "width 0.5s ease",
        }} />
      </div>

      {/* Summary stats */}
      <div style={{ display: "flex", gap: "12px", marginBottom: "24px", flexWrap: "wrap" }}>
        {[
          { label: "Total", value: batch.total, color: "#cdd6f4" },
          { label: "Completed", value: batch.completed, color: "#89b4fa" },
          { label: "Passed", value: batch.passed, color: "#a6e3a1" },
          { label: "Failed", value: batch.failed, color: "#f38ba8" },
          { label: "Pass Rate", value: `${passRate}%`, color: passRate >= 80 ? "#a6e3a1" : passRate >= 50 ? "#f9e2af" : "#f38ba8" },
        ].map(s => (
          <div key={s.label} style={{
            background: "#1e1e2e",
            border: "1px solid #313244",
            borderRadius: "10px",
            padding: "16px 20px",
            flex: 1,
            minWidth: "100px",
            textAlign: "center",
          }}>
            <div style={{ fontSize: "26px", fontWeight: "700", color: s.color }}>{s.value}</div>
            <div style={{ color: "#6c7086", fontSize: "12px", marginTop: "4px" }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* Run list */}
      <div style={{ background: "#1e1e2e", border: "1px solid #313244", borderRadius: "12px", overflow: "hidden" }}>
        <div style={{ padding: "16px 20px", borderBottom: "1px solid #313244" }}>
          <h2 style={{ color: "#cdd6f4", fontSize: "16px", margin: 0 }}>
            Runs ({batch.runs?.length || 0})
          </h2>
        </div>
        {(batch.runs || []).length === 0 ? (
          <p style={{ color: "#6c7086", padding: "24px" }}>No runs yet...</p>
        ) : (
          <div>
            {batch.runs.map(run => (
              <div key={run.run_id} style={{
                padding: "14px 20px",
                borderBottom: "1px solid #181825",
                display: "flex",
                alignItems: "flex-start",
                gap: "12px",
              }}>
                {/* Status badge */}
                <span style={{
                  background: statusBg[run.status] || "#1e1e2e",
                  color: statusColor[run.status] || "#cdd6f4",
                  borderRadius: "6px",
                  padding: "2px 10px",
                  fontSize: "12px",
                  fontWeight: "600",
                  flexShrink: 0,
                  marginTop: "2px",
                }}>
                  {run.status}
                </span>

                {/* Description */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{
                    color: "#cdd6f4",
                    fontSize: "14px",
                    margin: "0 0 4px 0",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}>
                    {run.description}
                  </p>
                  {run.error_message && (
                    <p style={{ color: "#f38ba8", fontSize: "12px", margin: 0 }}>
                      ⚠ {run.error_message}
                    </p>
                  )}
                  {run.live_url && (
                    <a href={run.live_url} target="_blank" rel="noreferrer"
                      style={{ color: "#89b4fa", fontSize: "12px" }}>
                      🔗 {run.live_url}
                    </a>
                  )}
                </div>

                {/* Build time */}
                {run.build_time_seconds != null && (
                  <span style={{ color: "#6c7086", fontSize: "12px", flexShrink: 0 }}>
                    {run.build_time_seconds}s
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

const backBtn = {
  background: "transparent",
  border: "1px solid #313244",
  borderRadius: "8px",
  color: "#6c7086",
  padding: "6px 14px",
  cursor: "pointer",
  fontSize: "13px",
};
