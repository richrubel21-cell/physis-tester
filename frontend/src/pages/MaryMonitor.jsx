import { useState } from "react";
import { api } from "../api/services";

const statusColor = {
  passed: "#a6e3a1",
  failed: "#f38ba8",
  error:  "#fab387",
};

const statusBg = {
  passed: "#1e3a2e",
  failed: "#3a1e1e",
  error:  "#3a2a1e",
};

const criteriaLabels = {
  responded_ok:  "Responded",
  speakable_ok:  "Speakable",
  context_ok:    "Context-aware",
  persona_ok:    "In persona",
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

export default function MaryMonitor({ result, onBack }) {
  // result is the full response from POST /mary/batch
  // It arrives already complete — no polling needed (Mary tests run synchronously)

  if (!result) return (
    <div style={{ color: "#f38ba8", padding: "48px", textAlign: "center" }}>
      No Mary batch data found.
      <br />
      <button onClick={onBack} style={{ ...backBtn, marginTop: "16px" }}>← Back</button>
    </div>
  );

  const passRate  = result.pass_rate ?? 0;
  const barColor  = passRate >= 80 ? "#a6e3a1" : passRate >= 50 ? "#f9e2af" : "#f38ba8";

  return (
    <div style={{ maxWidth: "960px", margin: "0 auto", padding: "32px 16px" }}>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "16px", marginBottom: "24px" }}>
        <button onClick={onBack} style={backBtn}>← Back</button>
        <h1 style={{ color: "#cdd6f4", fontSize: "22px", margin: 0 }}>
          🦋 Mary Test Batch
          <span style={{
            marginLeft: "12px",
            fontSize: "13px",
            background: passRate >= 80 ? "#1e3a2e" : passRate >= 50 ? "#2a2a1e" : "#3a1e1e",
            color: barColor,
            borderRadius: "6px",
            padding: "2px 10px",
            fontWeight: "600",
          }}>
            {passRate}% pass rate
          </span>
        </h1>
      </div>

      {/* Pass rate bar */}
      <div style={{ background: "#181825", borderRadius: "8px", height: "10px", marginBottom: "24px", overflow: "hidden" }}>
        <div style={{
          background: barColor,
          width: `${passRate}%`,
          height: "100%",
          transition: "width 0.5s ease",
        }} />
      </div>

      {/* Summary stats */}
      <div style={{ display: "flex", gap: "12px", marginBottom: "24px", flexWrap: "wrap" }}>
        {[
          { label: "Total Prompts",    value: result.total,              color: "#cdd6f4" },
          { label: "Passed",           value: result.passed,             color: "#a6e3a1" },
          { label: "Failed",           value: result.failed,             color: "#f38ba8" },
          { label: "Pass Rate",        value: `${passRate}%`,            color: barColor  },
          { label: "Total Time",       value: `${result.total_time_seconds}s`, color: "#89b4fa" },
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

      {/* Tested at */}
      {result.tested_at && (
        <p style={{ color: "#6c7086", fontSize: "12px", marginBottom: "20px" }}>
          Tested at: {new Date(result.tested_at).toLocaleString()}
        </p>
      )}

      {/* Results list */}
      <div style={{ background: "#1e1e2e", border: "1px solid #313244", borderRadius: "12px", overflow: "hidden" }}>
        <div style={{ padding: "16px 20px", borderBottom: "1px solid #313244" }}>
          <h2 style={{ color: "#cdd6f4", fontSize: "16px", margin: 0 }}>
            Prompt Results ({result.results?.length || 0})
          </h2>
        </div>

        {(result.results || []).map((r, i) => (
          <div key={i} style={{
            padding: "18px 20px",
            borderBottom: "1px solid #181825",
          }}>
            {/* Screen + status */}
            <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "10px" }}>
              <span style={{
                background: statusBg[r.overall_pass ? "passed" : "failed"] || "#1e1e2e",
                color: statusColor[r.overall_pass ? "passed" : "failed"] || "#cdd6f4",
                borderRadius: "6px",
                padding: "2px 10px",
                fontSize: "12px",
                fontWeight: "600",
                flexShrink: 0,
              }}>
                {r.overall_pass ? "PASS" : "FAIL"}
              </span>
              <span style={{
                background: "#181825",
                border: "1px solid #313244",
                borderRadius: "6px",
                padding: "2px 10px",
                fontSize: "12px",
                color: "#89b4fa",
                fontWeight: "600",
              }}>
                🦋 {r.screen}
              </span>
              {r.response_time_seconds != null && (
                <span style={{ color: "#6c7086", fontSize: "12px", marginLeft: "auto" }}>
                  {r.response_time_seconds}s
                </span>
              )}
            </div>

            {/* Prompt */}
            <p style={{ color: "#6c7086", fontSize: "12px", marginBottom: "6px", fontStyle: "italic" }}>
              Prompt: "{r.prompt}"
            </p>

            {/* Response */}
            {r.response_text && (
              <p style={{
                color: "#cdd6f4",
                fontSize: "13px",
                lineHeight: "1.6",
                marginBottom: "12px",
                background: "#181825",
                borderRadius: "8px",
                padding: "10px 14px",
                border: "1px solid #313244",
              }}>
                {r.response_text}
              </p>
            )}

            {/* Error message */}
            {r.error_message && (
              <p style={{ color: "#f38ba8", fontSize: "12px", marginBottom: "10px" }}>
                ⚠ {r.error_message}
              </p>
            )}

            {/* Criteria badges */}
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
              {Object.entries(criteriaLabels).map(([key, label]) => {
                const pass = r[key];
                return (
                  <span key={key} style={{
                    fontSize: "11px",
                    fontWeight: "600",
                    padding: "2px 10px",
                    borderRadius: "20px",
                    background: pass ? "#1e3a2e" : "#3a1e1e",
                    color: pass ? "#a6e3a1" : "#f38ba8",
                    border: `1px solid ${pass ? "#a6e3a1" : "#f38ba8"}`,
                  }}>
                    {pass ? "✓" : "✗"} {label}
                  </span>
                );
              })}
              <span style={{
                fontSize: "11px",
                fontWeight: "700",
                padding: "2px 10px",
                borderRadius: "20px",
                background: "#181825",
                color: "#89b4fa",
                border: "1px solid #313244",
              }}>
                Score: {r.score}/4
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
