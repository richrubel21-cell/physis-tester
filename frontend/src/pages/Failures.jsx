import { useState, useEffect } from "react";
import { api } from "../api/services";

export default function Failures({ onBack }) {
  const [failures, setFailures] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getFailures()
      .then(d => setFailures(d.failures || []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ maxWidth: "960px", margin: "0 auto", padding: "32px 16px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "16px", marginBottom: "24px" }}>
        <button onClick={onBack} style={backBtn}>← Back</button>
        <h1 style={{ color: "#cdd6f4", fontSize: "22px", margin: 0 }}>
          ⚠ Failure Log
        </h1>
      </div>

      {loading ? (
        <p style={{ color: "#6c7086" }}>Loading...</p>
      ) : failures.length === 0 ? (
        <div style={{
          background: "#1e3a2e",
          border: "1px solid #a6e3a1",
          borderRadius: "12px",
          padding: "32px",
          textAlign: "center",
          color: "#a6e3a1",
        }}>
          🎉 No failures recorded
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {failures.map(f => (
            <div key={f.run_id} style={{
              background: "#1e1e2e",
              border: "1px solid #3a1e1e",
              borderRadius: "10px",
              padding: "16px 20px",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
                <span style={{ color: "#6c7086", fontSize: "12px" }}>Run #{f.run_id}</span>
                <span style={{
                  background: f.status === "error" ? "#3a2a1e" : "#3a1e1e",
                  color: f.status === "error" ? "#fab387" : "#f38ba8",
                  borderRadius: "6px",
                  padding: "2px 10px",
                  fontSize: "12px",
                  fontWeight: "600",
                }}>
                  {f.status}
                </span>
              </div>
              <p style={{ color: "#cdd6f4", fontSize: "14px", margin: "0 0 8px 0" }}>
                {f.description}
              </p>
              {f.error_message && (
                <div style={{
                  background: "#181825",
                  borderRadius: "6px",
                  padding: "10px 14px",
                  color: "#f38ba8",
                  fontSize: "13px",
                  fontFamily: "monospace",
                }}>
                  {f.error_message}
                </div>
              )}
              <div style={{ display: "flex", gap: "16px", marginTop: "8px" }}>
                {f.build_time_seconds != null && (
                  <span style={{ color: "#6c7086", fontSize: "12px" }}>
                    ⏱ {f.build_time_seconds}s
                  </span>
                )}
                <span style={{ color: "#6c7086", fontSize: "12px" }}>
                  {new Date(f.started_at).toLocaleString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
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
