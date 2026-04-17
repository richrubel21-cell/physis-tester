import { useState, useEffect } from "react";
import { api } from "../api/services";
import { usePoll } from "../hooks/usePoll";
import EcosystemApproveModal from "../EcosystemApproveModal";

const statusColor = {
  passed:  "#a6e3a1",
  failed:  "#f38ba8",
  error:   "#fab387",
  running: "#89b4fa",
  pending: "#6c7086",
};

const statusBg = {
  passed:  "#1e3a2e",
  failed:  "#3a1e1e",
  error:   "#3a2a1e",
  running: "#1e2a3a",
  pending: "#1e1e2e",
};

const backBtn = {
  background: "transparent",
  border:     "1px solid #313244",
  borderRadius: "8px",
  color:      "#6c7086",
  padding:    "6px 14px",
  cursor:     "pointer",
  fontSize:   "13px",
};

export default function EcosystemMonitor({ batchId, onBack }) {
  const [batch, setBatch]           = useState(null);
  const [loading, setLoading]       = useState(true);
  const [hasFetched, setHasFetched] = useState(false);
  const [expanded, setExpanded]     = useState({});   // run_id -> bool
  const [approveRun, setApproveRun] = useState(null); // run object when modal open

  // Stop polling on any terminal batch state — same pattern as BatchMonitor
  const isRunning = batch
    ? !["completed", "failed", "cancelled"].includes(batch.status)
    : false;

  async function fetchBatch() {
    try {
      const data = await api.getEcosystemBatch(batchId);
      setBatch(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
      setHasFetched(true);
    }
  }

  useEffect(() => { fetchBatch(); }, [batchId]);
  usePoll(fetchBatch, 4000, isRunning && hasFetched);

  if (loading) return (
    <div style={{ color: "#6c7086", padding: "48px", textAlign: "center" }}>
      Loading ecosystem batch #{batchId}...
    </div>
  );

  if (!batch) return (
    <div style={{ color: "#f38ba8", padding: "48px", textAlign: "center" }}>
      Ecosystem batch not found.
      <button onClick={onBack} style={backBtn}>← Back</button>
    </div>
  );

  const completed = batch.completed || 0;
  const total     = batch.scenario_count || 0;
  const progressPct = total > 0 ? Math.round((completed / total) * 100) : 0;
  const passRate  = total > 0 ? Math.round(((batch.pass_count || 0) / total) * 100) : 0;

  const passColor = passRate >= 80 ? "#a6e3a1" : passRate >= 50 ? "#f9e2af" : "#f38ba8";

  return (
    <div style={{ maxWidth: "1100px", margin: "0 auto", padding: "32px 16px" }}>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "16px", marginBottom: "8px" }}>
        <button onClick={onBack} style={backBtn}>← Back</button>
        <h1 style={{ color: "#cdd6f4", fontSize: "22px", margin: 0 }}>
          🌐 Ecosystem Batch #{batchId}
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

      <div style={{ color: "#6c7086", fontSize: "13px", marginBottom: "20px" }}>
        <span style={{ background: batch.type === "full" ? "#2a4a3f" : "#4a3f2a", color: batch.type === "full" ? "#94e2d5" : "#f9e2af", borderRadius: "6px", padding: "2px 10px", fontSize: "11px", fontWeight: "600", marginRight: "10px" }}>
          {batch.type}
        </span>
        {batch.app_count} apps per scenario · {total} scenarios total · 29 tests per app + 8 integration tests
        {batch.marketplace_eligible && (
          <span style={{ marginLeft: "10px", background: "#1e3a2e", color: "#a6e3a1", borderRadius: "6px", padding: "2px 10px", fontSize: "11px", fontWeight: "700" }}>
            ✓ Marketplace Eligible
          </span>
        )}
      </div>

      {/* Progress bar */}
      <div style={{ background: "#181825", borderRadius: "8px", height: "10px", marginBottom: "20px", overflow: "hidden" }}>
        <div style={{
          background:  passColor,
          width:       `${progressPct}%`,
          height:      "100%",
          transition:  "width 0.5s ease",
        }} />
      </div>

      {/* Summary stats */}
      <div style={{ display: "flex", gap: "12px", marginBottom: "24px", flexWrap: "wrap" }}>
        {[
          { label: "Scenarios",   value: total,                    color: "#cdd6f4" },
          { label: "Completed",   value: completed,                color: "#89b4fa" },
          { label: "Passed",      value: batch.pass_count ?? 0,    color: "#a6e3a1" },
          { label: "Failed",      value: batch.fail_count ?? 0,    color: "#f38ba8" },
          { label: "Pass Rate",   value: `${passRate}%`,           color: passColor },
          { label: "Avg Build",   value: batch.avg_build_time ? `${batch.avg_build_time}s` : "—", color: "#94e2d5" },
        ].map(s => (
          <div key={s.label} style={{
            background: "#1e1e2e",
            border:     "1px solid #313244",
            borderRadius: "10px",
            padding:    "16px 20px",
            flex:       1,
            minWidth:   "120px",
            textAlign:  "center",
          }}>
            <div style={{ fontSize: "24px", fontWeight: "700", color: s.color }}>{s.value}</div>
            <div style={{ color: "#6c7086", fontSize: "12px", marginTop: "4px" }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* Run list */}
      <div style={{ background: "#1e1e2e", border: "1px solid #313244", borderRadius: "12px", overflow: "hidden" }}>
        <div style={{ padding: "14px 20px", borderBottom: "1px solid #313244" }}>
          <h2 style={{ color: "#cdd6f4", fontSize: "16px", margin: 0 }}>
            Scenarios ({batch.runs?.length || 0})
          </h2>
        </div>
        {(batch.runs || []).length === 0 ? (
          <p style={{ color: "#6c7086", padding: "24px" }}>No scenarios yet...</p>
        ) : (
          <div>
            {batch.runs.map(run => {
              const open = !!expanded[run.run_id];
              return (
                <div key={run.run_id} style={{ borderBottom: "1px solid #181825" }}>

                  {/* Row header */}
                  <div
                    onClick={() => setExpanded(prev => ({ ...prev, [run.run_id]: !open }))}
                    style={{
                      padding: "14px 20px",
                      display: "flex",
                      alignItems: "flex-start",
                      gap: "12px",
                      cursor: "pointer",
                    }}
                  >
                    <span style={{
                      background: statusBg[run.status] || "#1e1e2e",
                      color:      statusColor[run.status] || "#cdd6f4",
                      borderRadius: "6px",
                      padding:    "2px 10px",
                      fontSize:   "12px",
                      fontWeight: "600",
                      flexShrink: 0,
                      marginTop:  "2px",
                    }}>
                      {run.status}
                    </span>

                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ color: "#cdd6f4", fontSize: "14px", margin: "0 0 4px 0", lineHeight: 1.4 }}>
                        {run.business_description}
                      </p>
                      <div style={{ color: "#6c7086", fontSize: "12px", display: "flex", gap: "14px", flexWrap: "wrap" }}>
                        <span>{run.apps_deployed}/{run.apps_planned} apps deployed</span>
                        <span>{run.apps_integrated}/{run.apps_planned} integrated</span>
                        {run.total_time_seconds != null && <span>{run.total_time_seconds}s</span>}
                        <span>{open ? "▴ hide" : "▾ details"}</span>
                      </div>
                      {run.fail_reason && (
                        <p style={{ color: "#f38ba8", fontSize: "12px", margin: "6px 0 0 0" }}>
                          ⚠ {run.fail_reason}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Expanded details */}
                  {open && (
                    <div style={{ padding: "0 20px 18px 42px", background: "#181825" }}>

                      {/* Planned apps */}
                      {(run.apps_planned_json || []).length > 0 && (
                        <div style={{ marginTop: "12px" }}>
                          <div style={{ color: "#6c7086", fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "6px", fontWeight: "600" }}>
                            AI Plan ({run.apps_planned_json.length} apps)
                          </div>
                          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                            {run.apps_planned_json.map((a, i) => (
                              <div key={i} style={{ fontSize: "12px", color: "#cdd6f4", lineHeight: 1.5 }}>
                                <span style={{ color: "#94e2d5", fontWeight: "600" }}>{a.name}</span>
                                <span style={{ color: "#6c7086" }}> · {a.template_category}</span>
                                <div style={{ color: "#a6adc8", marginLeft: "0", marginTop: "2px" }}>{a.purpose}</div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Per-app build outcome */}
                      {(run.apps_detail || []).length > 0 && (
                        <div style={{ marginTop: "14px" }}>
                          <div style={{ color: "#6c7086", fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "6px", fontWeight: "600" }}>
                            Build Outcomes
                          </div>
                          <table style={{ width: "100%", borderCollapse: "collapse" }}>
                            <thead>
                              <tr style={{ borderBottom: "1px solid #313244" }}>
                                {["App", "Category", "Status", "Live URL", "Build Time"].map(h => (
                                  <th key={h} style={{ color: "#6c7086", fontSize: "11px", textAlign: "left", padding: "6px 8px", fontWeight: "600" }}>{h}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {run.apps_detail.map((a, i) => (
                                <tr key={i} style={{ borderBottom: "1px solid #11111b" }}>
                                  <td style={{ color: "#cdd6f4", padding: "6px 8px", fontSize: "12px" }}>{a.name || "—"}</td>
                                  <td style={{ color: "#6c7086", padding: "6px 8px", fontSize: "12px" }}>{a.category || "—"}</td>
                                  <td style={{ padding: "6px 8px" }}>
                                    <span style={{
                                      background: statusBg[a.status] || "#1e1e2e",
                                      color:      statusColor[a.status] || "#cdd6f4",
                                      borderRadius: "5px",
                                      padding: "1px 8px",
                                      fontSize: "11px",
                                      fontWeight: "600",
                                    }}>
                                      {a.status || "—"}
                                    </span>
                                  </td>
                                  <td style={{ padding: "6px 8px", fontSize: "12px" }}>
                                    {a.live_url ? (
                                      <a href={a.live_url} target="_blank" rel="noreferrer" style={{ color: "#89b4fa" }}>
                                        🔗 open
                                      </a>
                                    ) : (
                                      <span style={{ color: "#6c7086" }}>—</span>
                                    )}
                                  </td>
                                  <td style={{ color: "#6c7086", padding: "6px 8px", fontSize: "12px" }}>
                                    {a.build_time != null ? `${a.build_time}s` : "—"}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}

                      {/* Ecosystem integration summary */}
                      <div style={{ marginTop: "14px", fontSize: "12px", color: "#cdd6f4" }}>
                        <span style={{ color: "#6c7086" }}>Ecosystem Integration:</span>{" "}
                        <span style={{ color: run.apps_integrated === run.apps_planned && run.apps_planned > 0 ? "#a6e3a1" : "#f9e2af" }}>
                          {run.apps_integrated}/{run.apps_planned} apps
                        </span>
                      </div>

                      {/* Integration tests (22–29) */}
                      {(run.apps_planned > 0) && (
                        <div style={{ marginTop: "18px", background: "#11111b", border: "1px solid #313244", borderRadius: "10px", padding: "14px 16px" }}>
                          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "8px" }}>
                            <div style={{ color: "#cdd6f4", fontSize: "13px", fontWeight: "700" }}>🔗 Integration Tests</div>
                            <span style={{
                              background:   run.integration_passed ? "#1e3a2e" : "#3a1e1e",
                              color:        run.integration_passed ? "#a6e3a1" : "#f38ba8",
                              borderRadius: "6px",
                              padding:      "2px 10px",
                              fontSize:     "11px",
                              fontWeight:   "700",
                            }}>
                              {run.integration_passed ? `INTEGRATION PASSED ${run.integration_score}/8` : `INTEGRATION FAILED ${run.integration_score ?? 0}/8`}
                            </span>
                          </div>
                          {/* Progress bar */}
                          <div style={{ background: "#181825", borderRadius: "6px", height: "6px", marginBottom: "10px", overflow: "hidden" }}>
                            <div style={{
                              background: run.integration_passed ? "#a6e3a1" : "#f9e2af",
                              width:      `${((run.integration_score ?? 0) / 8) * 100}%`,
                              height:     "100%",
                              transition: "width 0.5s ease",
                            }} />
                          </div>
                          {(run.integration_tests || []).length === 0 ? (
                            <div style={{ color: "#6c7086", fontSize: "12px" }}>
                              {run.integration_details || "Integration tests not yet run for this ecosystem."}
                            </div>
                          ) : (
                            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                              {run.integration_tests.map(t => (
                                <div key={t.test_id} style={{ fontSize: "12px", lineHeight: 1.5, color: t.passed ? "#a6e3a1" : "#f38ba8" }}>
                                  <span style={{ fontFamily: "monospace", marginRight: "6px" }}>{t.passed ? "✅" : "❌"}</span>
                                  <span style={{ color: "#cdd6f4", fontWeight: "600" }}>#{t.test_id} {t.name}</span>
                                  {!t.passed && t.detail && (
                                    <div style={{ color: "#f38ba8", fontSize: "11px", marginLeft: "24px", marginTop: "2px" }}>
                                      {t.detail}
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                          {run.marketplace_eligible && (
                            <div style={{ marginTop: "14px", display: "flex", alignItems: "center", gap: "10px" }}>
                              <span style={{ background: "#1e3a2e", color: "#a6e3a1", borderRadius: "6px", padding: "3px 10px", fontSize: "11px", fontWeight: "700" }}>
                                ✓ Marketplace Eligible
                              </span>
                              <button
                                type="button"
                                onClick={e => { e.stopPropagation(); setApproveRun(run); }}
                                style={{ background: "#7c3aed", color: "white", border: "none", borderRadius: "8px", padding: "7px 14px", fontSize: "12px", fontWeight: "700", cursor: "pointer" }}
                              >
                                ✓ Approve Ecosystem for Marketplace
                              </button>
                            </div>
                          )}
                        </div>
                      )}

                      {run.error_message && (
                        <div style={{ marginTop: "10px", fontSize: "12px", color: "#f38ba8" }}>
                          Error: {run.error_message}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {approveRun && (
        <EcosystemApproveModal
          run={approveRun}
          onClose={() => setApproveRun(null)}
        />
      )}
    </div>
  );
}
