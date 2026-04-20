import { useState, useEffect } from "react";
import { api } from "../api/services";
import { usePoll } from "../hooks/usePoll";
import ApproveModal from "../ApproveModal";
import PromoteToTemplateModal from "../PromoteToTemplateModal";

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
  const [approveRun, setApproveRun] = useState(null);
  const [promoteRun, setPromoteRun] = useState(null);

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

                {/* Approve button — passed proof + live_url are required;
                    validity + Powered-by-Physis (Test 35) gate is enforced
                    below in the AppValidityPanel rendering. */}
                {run.status === "passed"
                    && run.live_url
                    && run.validity_passed
                    && run.powered_by_physis && (
                  <button
                    type="button"
                    onClick={() => setApproveRun(run)}
                    style={{
                      background: "#7c3aed",
                      color: "white",
                      border: "none",
                      borderRadius: "6px",
                      padding: "4px 10px",
                      fontSize: "11px",
                      fontWeight: "700",
                      cursor: "pointer",
                      flexShrink: 0,
                    }}
                  >
                    ✓ Approve for Marketplace
                  </button>
                )}

                {/* Promote to Template — gold button, gated on the strict
                    quality bar: passed status + validity + Powered-by-Physis +
                    proof_score >= 18. proof_score is read off the run; if the
                    single-app pipeline hasn't started writing it yet, the
                    button stays hidden so we never promote unverified builds. */}
                {run.status === "passed"
                    && run.live_url
                    && run.validity_passed
                    && run.powered_by_physis
                    && (run.proof_score ?? 0) >= 18 && (
                  <button
                    type="button"
                    onClick={() => setPromoteRun(run)}
                    style={{
                      background: "#F59E0B",
                      color: "white",
                      border: "none",
                      borderRadius: "10px",
                      padding: "4px 10px",
                      fontSize: "11px",
                      fontWeight: "700",
                      cursor: "pointer",
                      flexShrink: 0,
                      boxShadow: "0 2px 6px rgba(245,158,11,0.30)",
                    }}
                  >
                    ⭐ Promote to Template
                  </button>
                )}
              </div>
            ))}
            {/* App Validity panels — rendered below the row so the run
                table stays scannable. Surfaces the 7 tests + the strict
                "Powered by Physis" alert when Test 35 fails. */}
            {batch.runs.some(r => r.live_url) && (
              <div style={{
                padding: "16px 20px",
                borderTop: "1px solid #181825",
                background: "#11111b",
                color: "#6c7086",
                fontSize: "11px",
                letterSpacing: "0.05em",
                textTransform: "uppercase",
                fontWeight: "700",
              }}>
                App Validity Per Run · 21 Proof Tests + 7 Validity Tests = 28 Total
              </div>
            )}
            {batch.runs.filter(r => r.live_url).map(run => (
              <AppValidityPanel key={`val-${run.run_id}`} run={run} />
            ))}
          </div>
        )}
      </div>

      {approveRun && (
        <ApproveModal run={approveRun} onClose={() => setApproveRun(null)} />
      )}

      {promoteRun && (
        <PromoteToTemplateModal run={promoteRun} onClose={() => setPromoteRun(null)} />
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


// ─── App Validity panel — tests 30-36 results for a single run ────────────
// Renders below each run row in BatchMonitor. Shows the 7 tests with
// pass/fail dots, an APP WORKS / APP BROKEN summary badge, the missing-
// Powered-by-Physis red alert when Test 35 fails, and the combined
// proof + validity = 28 score line.
function AppValidityPanel({ run }) {
  const tests   = Array.isArray(run.validity_tests) ? run.validity_tests : [];
  const score   = run.validity_score ?? 0;
  const passed  = !!run.validity_passed;
  const powered = !!run.powered_by_physis;
  const missingBadge = tests.length > 0 && !powered;

  return (
    <div style={{
      padding: "14px 20px 18px 20px",
      borderBottom: "1px solid #181825",
      background: "#11111b",
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px", marginBottom: "10px", flexWrap: "wrap" }}>
        <div style={{ color: "#cdd6f4", fontSize: "13px", fontWeight: "700" }}>
          ⚡ App Validity Tests · Run #{run.run_id}
        </div>
        <span style={{
          background:   passed ? "#1e3a2e" : "#3a1e1e",
          color:        passed ? "#a6e3a1" : "#f38ba8",
          borderRadius: "6px",
          padding:      "2px 10px",
          fontSize:     "11px",
          fontWeight:   "700",
        }}>
          {passed ? `APP WORKS ✅ ${score}/7` : `APP BROKEN ❌ ${score}/7`}
        </span>
      </div>

      {/* Progress bar */}
      <div style={{ background: "#181825", borderRadius: "6px", height: "6px", marginBottom: "10px", overflow: "hidden" }}>
        <div style={{
          background: passed ? "#a6e3a1" : (score > 0 ? "#f9e2af" : "#f38ba8"),
          width:      `${(score / 7) * 100}%`,
          height:     "100%",
          transition: "width 0.4s ease",
        }} />
      </div>

      {tests.length === 0 ? (
        <div style={{ color: "#6c7086", fontSize: "12px" }}>
          Validity tests not yet run for this build.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          {tests.map(t => (
            <div key={t.test_id} style={{
              fontSize: "12px",
              lineHeight: 1.5,
              color: t.passed ? "#a6e3a1" : "#f38ba8",
            }}>
              <span style={{ fontFamily: "monospace", marginRight: "6px" }}>
                {t.passed ? "✅" : "❌"}
              </span>
              <span style={{ color: "#cdd6f4", fontWeight: "600" }}>
                #{t.test_id} {t.name}
              </span>
              {!t.passed && t.detail && (
                <div style={{ color: "#f38ba8", fontSize: "11px", marginLeft: "24px", marginTop: "2px" }}>
                  {t.detail}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {missingBadge && (
        <div style={{
          marginTop: "10px",
          padding: "8px 12px",
          background: "#3a1e1e",
          border: "1px solid #f38ba8",
          borderRadius: "6px",
          color: "#f38ba8",
          fontSize: "12px",
          fontWeight: "700",
        }}>
          🚨 MISSING: Powered by Physis — never acceptable for marketplace
        </div>
      )}

      <div style={{
        marginTop: "10px",
        color: "#6c7086",
        fontSize: "11px",
        letterSpacing: "0.04em",
      }}>
        21 Proof Tests + 7 Validity Tests = 28 Total
      </div>
    </div>
  );
}
