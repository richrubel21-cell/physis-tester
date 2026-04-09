import { useState, useEffect } from "react";
import { api } from "../api/services";
import { usePoll } from "../hooks/usePoll";

const criteriaLabels = {
  responded_ok:  "Responded",
  speakable_ok:  "Speakable",
  context_ok:    "Context-aware",
  persona_ok:    "In persona",
  length_ok:     "Good length",
  helpful_ok:    "Helpful",
  tone_ok:       "Warm tone",
};

const backBtn = {
  background: "transparent",
  border: "1px solid #313244",
  borderRadius: "8px",
  color: "#6c7086",
  padding: "6px 14px",
  cursor: "pointer",
  fontSize: "13px",
};

export default function MaryMonitor({ batchId, onBack }) {
  const [batch,      setBatch]      = useState(null);
  const [loading,    setLoading]    = useState(true);
  const [hasFetched, setHasFetched] = useState(false);

  // Stop polling on any terminal state
  const isRunning = batch
    ? !["completed", "failed", "cancelled"].includes(batch.status)
    : false;

  async function fetchBatch() {
    try {
      const data = await api.getMaryBatch(batchId);
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
      Loading Mary batch #{batchId}...
    </div>
  );

  if (!batch) return (
    <div style={{ color: "#f38ba8", padding: "48px", textAlign: "center" }}>
      Mary batch not found.
      <br />
      <button onClick={onBack} style={{ ...backBtn, marginTop: "16px" }}>← Back</button>
    </div>
  );

  const passRate = batch.pass_rate ?? 0;
  const barColor = passRate >= 80 ? "#a6e3a1" : passRate >= 50 ? "#f9e2af" : "#f38ba8";
  const progressPct = batch.total > 0 ? Math.round((batch.completed / batch.total) * 100) : 0;

  return (
    <div style={{ maxWidth: "960px", margin: "0 auto", padding: "32px 16px" }}>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "16px", marginBottom: "24px" }}>
        <button onClick={onBack} style={backBtn}>← Back</button>
        <h1 style={{ color: "#cdd6f4", fontSize: "22px", margin: 0 }}>
          🦋 Mary Batch #{batchId}
          <span style={{ marginLeft: "12px", fontSize: "13px", background: batch.status === "completed" ? "#1e3a2e" : "#1e2a3a", color: batch.status === "completed" ? "#a6e3a1" : "#89b4fa", borderRadius: "6px", padding: "2px 10px", fontWeight: "600" }}>
            {batch.status}
          </span>
        </h1>
        {isRunning && (
          <span style={{ color: "#89b4fa", fontSize: "13px", animation: "pulse 1.5s infinite" }}>● Live</span>
        )}
      </div>

      {/* Progress bar */}
      <div style={{ background: "#181825", borderRadius: "8px", height: "10px", marginBottom: "24px", overflow: "hidden" }}>
        <div style={{ background: barColor, width: `${progressPct}%`, height: "100%", transition: "width 0.5s ease" }} />
      </div>

      {/* Summary stats */}
      <div style={{ display: "flex", gap: "12px", marginBottom: "24px", flexWrap: "wrap" }}>
        {[
          { label: "Total Prompts", value: batch.total,              color: "#cdd6f4" },
          { label: "Completed",     value: batch.completed,          color: "#89b4fa" },
          { label: "Passed",        value: batch.passed,             color: "#a6e3a1" },
          { label: "Failed",        value: batch.failed,             color: "#f38ba8" },
          { label: "Pass Rate",     value: `${passRate}%`,           color: barColor  },
        ].map(s => (
          <div key={s.label} style={{ background: "#1e1e2e", border: "1px solid #313244", borderRadius: "10px", padding: "16px 20px", flex: 1, minWidth: "100px", textAlign: "center" }}>
            <div style={{ fontSize: "26px", fontWeight: "700", color: s.color }}>{s.value}</div>
            <div style={{ color: "#6c7086", fontSize: "12px", marginTop: "4px" }}>{s.label}</div>
          </div>
        ))}
      </div>

      {batch.finished_at && (
        <p style={{ color: "#6c7086", fontSize: "12px", marginBottom: "20px" }}>
          Completed: {new Date(batch.finished_at).toLocaleString()}
          {batch.use_ai && <span style={{ marginLeft: "12px", color: "#7c3aed" }}>✦ AI-generated prompts</span>}
        </p>
      )}

      {/* Results */}
      <div style={{ background: "#1e1e2e", border: "1px solid #313244", borderRadius: "12px", overflow: "hidden" }}>
        <div style={{ padding: "16px 20px", borderBottom: "1px solid #313244" }}>
          <h2 style={{ color: "#cdd6f4", fontSize: "16px", margin: 0 }}>
            Prompt Results ({batch.runs?.length || 0})
          </h2>
        </div>

        {(batch.runs || []).length === 0 ? (
          <p style={{ color: "#6c7086", padding: "24px" }}>
            {isRunning ? "Running — results will appear here as they complete..." : "No results yet."}
          </p>
        ) : (
          (batch.runs || []).map((r, i) => (
            <div key={r.run_id || i} style={{ padding: "18px 20px", borderBottom: "1px solid #181825" }}>

              {/* Screen + status + badges */}
              <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "10px", flexWrap: "wrap" }}>
                <span style={{
                  background: r.overall_pass ? "#1e3a2e" : r.status === "pending" ? "#1e2a3a" : "#3a1e1e",
                  color:      r.overall_pass ? "#a6e3a1" : r.status === "pending" ? "#89b4fa" : "#f38ba8",
                  borderRadius: "6px", padding: "2px 10px", fontSize: "12px", fontWeight: "600", flexShrink: 0,
                }}>
                  {r.status === "pending" ? "PENDING" : r.overall_pass ? "PASS" : "FAIL"}
                </span>
                <span style={{ background: "#181825", border: "1px solid #313244", borderRadius: "6px", padding: "2px 10px", fontSize: "12px", color: "#89b4fa", fontWeight: "600" }}>
                  🦋 {r.screen}
                </span>
                <span style={{ background: r.prompt_type === "specific" ? "#1e2a3a" : "#181825", border: `1px solid ${r.prompt_type === "specific" ? "#89b4fa" : "#313244"}`, borderRadius: "6px", padding: "2px 10px", fontSize: "11px", color: r.prompt_type === "specific" ? "#89b4fa" : "#6c7086", fontWeight: "600" }}>
                  {r.prompt_type === "specific" ? "💼 specific" : "❓ general"}
                </span>
                {r.source === "ai_generated" && (
                  <span style={{ background: "#2a1e3a", border: "1px solid #7c3aed", borderRadius: "6px", padding: "2px 10px", fontSize: "11px", color: "#c4b5fd", fontWeight: "600" }}>
                    ✦ AI prompt
                  </span>
                )}
                {r.response_time_seconds != null && (
                  <span style={{ color: "#6c7086", fontSize: "12px", marginLeft: "auto" }}>
                    {r.response_time_seconds}s
                  </span>
                )}
              </div>

              {/* Prompt */}
              <p style={{ color: "#6c7086", fontSize: "12px", marginBottom: "8px", fontStyle: "italic" }}>
                "{r.prompt}"
              </p>

              {/* Response */}
              {r.response_text && (
                <p style={{ color: "#cdd6f4", fontSize: "13px", lineHeight: "1.6", marginBottom: "12px", background: "#181825", borderRadius: "8px", padding: "10px 14px", border: "1px solid #313244" }}>
                  {r.response_text}
                </p>
              )}

              {/* Error */}
              {r.error_message && (
                <p style={{ color: "#f38ba8", fontSize: "12px", marginBottom: "10px" }}>⚠ {r.error_message}</p>
              )}

              {/* Criteria badges — only shown once run is complete */}
              {r.status !== "pending" && (
                <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                  {Object.entries(criteriaLabels).map(([key, label]) => {
                    const pass = r[key];
                    return (
                      <span key={key} style={{ fontSize: "11px", fontWeight: "600", padding: "2px 9px", borderRadius: "20px", background: pass ? "#1e3a2e" : "#3a1e1e", color: pass ? "#a6e3a1" : "#f38ba8", border: `1px solid ${pass ? "#a6e3a1" : "#f38ba8"}` }}>
                        {pass ? "✓" : "✗"} {label}
                      </span>
                    );
                  })}
                  <span style={{ fontSize: "11px", fontWeight: "700", padding: "2px 9px", borderRadius: "20px", background: "#181825", color: "#89b4fa", border: "1px solid #313244" }}>
                    Score: {r.score}/7
                  </span>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
