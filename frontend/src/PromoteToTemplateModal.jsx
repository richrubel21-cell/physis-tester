import { useState } from "react";

// PromoteToTemplateModal — submitted from the tester, lands in the main
// Physis backend's template_promotions table, then waits for admin review.
// Mirrors ApproveModal's auth pattern: the user pastes a Physis Bearer
// token once and we cache it in localStorage as physis_admin_token.

const PHYSIS_API = import.meta.env.VITE_PHYSIS_API || "https://physis.onrender.com";

const CATEGORIES = ["Generators", "Analyzers", "Trackers", "Assistants", "Transformers"];

// Warm cream design tokens — match the Physis dashboard palette so the
// modal feels native to the platform it's submitting into, not the dark
// tester chrome behind it.
const BG          = "#FAF7F2";
const CARD_BG     = "#FFFFFF";
const BORDER      = "#E8E0D5";
const TEXT        = "#1C1917";
const MUTED       = "#6B7280";
const VIOLET      = "#7C3AED";
const VIOLET_SOFT = "#F5F3FF";
const GOLD        = "#F59E0B";
const GOLD_SOFT   = "#FEF3C7";
const PLAYFAIR    = "'Playfair Display', Georgia, 'Times New Roman', serif";
const INTER       = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif";

export default function PromoteToTemplateModal({ run, onClose }) {
  // Pre-fill the name from the run's tool_name when present, otherwise
  // the first 60 chars of the description.
  const initialName = (
    run?.tool_name
    || run?.selectedName
    || (run?.description ? run.description.slice(0, 60) : "")
    || ""
  ).trim();

  const [name,        setName]        = useState(initialName);
  const [category,    setCategory]    = useState(CATEGORIES[0]);
  const [description, setDescription] = useState("");
  const [tagsText,    setTagsText]    = useState("");
  const [submitting,  setSubmitting]  = useState(false);
  const [success,     setSuccess]     = useState(false);
  const [error,       setError]       = useState("");
  const [token,       setToken]       = useState(
    () => (typeof window !== "undefined" ? (localStorage.getItem("physis_admin_token") || "") : "")
  );

  const proofScore    = run?.proof_score    ?? null;
  const validityScore = run?.validity_score ?? 0;

  // Subdomain best-effort from live_url
  let subdomain = run?.subdomain || null;
  if (!subdomain && run?.live_url) {
    try {
      subdomain = new URL(run.live_url).hostname.split(".")[0] || null;
    } catch { /* ignore */ }
  }

  async function handleSubmit() {
    setError("");
    if (!name.trim()) { setError("Template name is required."); return; }
    if (name.length > 60) { setError("Template name must be 60 characters or fewer."); return; }
    if (!category) { setError("Pick a category."); return; }
    if (description.length > 200) { setError("Description must be 200 characters or fewer."); return; }
    if (!token.trim()) { setError("Paste a Physis Bearer token to authorize this submission."); return; }

    localStorage.setItem("physis_admin_token", token.trim());
    setSubmitting(true);
    try {
      const tags = tagsText.split(",").map(t => t.trim()).filter(Boolean);
      const res = await fetch(`${PHYSIS_API}/api/templates/promote`, {
        method: "POST",
        headers: {
          "Content-Type":  "application/json",
          Authorization:   `Bearer ${token.trim()}`,
        },
        body: JSON.stringify({
          build_id:       run?.build_id || run?.run_id ? String(run.build_id || run.run_id) : null,
          live_url:       run?.live_url || null,
          subdomain,
          tool_name:      name.trim(),
          category,
          description:    description.trim(),
          tags,
          proof_score:    proofScore != null ? Number(proofScore) : 0,
          validity_score: Number(validityScore || 0),
        }),
      });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new Error(`HTTP ${res.status}: ${body.slice(0, 300)}`);
      }
      setSuccess(true);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div onClick={onClose} style={{
      position: "fixed", inset: 0, background: "rgba(28, 25, 23, 0.55)",
      display: "flex", alignItems: "center", justifyContent: "center",
      padding: 20, zIndex: 9999, fontFamily: INTER,
    }}>
      <link
        href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700;900&family=Inter:wght@300;400;500;600;700&display=swap"
        rel="stylesheet"
      />
      <div onClick={(e) => e.stopPropagation()} style={{
        background: BG, borderRadius: 20, maxWidth: 580, width: "100%",
        boxShadow: "0 30px 80px rgba(28, 25, 23, 0.35)", overflow: "hidden",
        maxHeight: "92vh", display: "flex", flexDirection: "column",
        border: `1px solid ${BORDER}`,
      }}>
        {/* Header */}
        <div style={{
          padding: "20px 26px", borderBottom: `1px solid ${BORDER}`, background: CARD_BG,
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <div>
            <div style={{ fontFamily: PLAYFAIR, fontSize: 22, fontWeight: 700, color: TEXT }}>
              Promote to Template
            </div>
            <div style={{ fontSize: 12, color: MUTED, marginTop: 4, lineHeight: 1.5 }}>
              Submit this passing build for inclusion in the Physis template library.
            </div>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" style={{
            background: "transparent", border: "none", color: MUTED,
            fontSize: 26, cursor: "pointer", lineHeight: 1, padding: 4, fontFamily: INTER,
          }}>×</button>
        </div>

        {/* Body */}
        <div style={{ padding: "22px 26px", overflowY: "auto" }}>
          {success ? (
            <div style={{
              background: CARD_BG, border: `2px solid ${GOLD}`, borderRadius: 16,
              padding: "26px 22px", textAlign: "center",
            }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>⭐</div>
              <div style={{ fontFamily: PLAYFAIR, fontSize: 22, fontWeight: 700, color: TEXT, marginBottom: 8 }}>
                ✅ Template promoted successfully!
              </div>
              <div style={{ fontSize: 13, color: MUTED, lineHeight: 1.6 }}>
                It will appear in the Physis pipeline after admin review.
              </div>
              <button type="button" onClick={onClose} style={{
                marginTop: 18,
                background: VIOLET, color: "#FFFFFF", border: "none",
                borderRadius: 10, padding: "10px 22px", fontSize: 13, fontWeight: 600,
                cursor: "pointer", fontFamily: INTER,
              }}>
                Close
              </button>
            </div>
          ) : (
            <>
              {/* Quality rating display (read-only) */}
              <div style={{
                background: VIOLET_SOFT, border: `1px solid #DDD6FE`, borderRadius: 12,
                padding: "12px 14px", marginBottom: 18,
                display: "flex", alignItems: "center", justifyContent: "space-between",
                flexWrap: "wrap", gap: 8,
              }}>
                <div style={{ fontSize: 12, color: TEXT, fontWeight: 600 }}>Quality rating</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <ScoreBadge label="Proof"    score={proofScore != null ? `${proofScore}/21` : "—"} ok={proofScore == null || proofScore >= 18} />
                  <ScoreBadge label="Validity" score={`${validityScore}/7`} ok={Number(validityScore) >= 5} />
                  {Number(validityScore) >= 5 && (proofScore == null || proofScore >= 18) && (
                    <span style={{
                      background: "#D1FAE5", color: "#065F46",
                      borderRadius: 999, padding: "4px 10px", fontSize: 11, fontWeight: 700,
                    }}>
                      Eligible to promote ✅
                    </span>
                  )}
                </div>
              </div>

              {/* Name */}
              <div style={{ marginBottom: 14 }}>
                <Label>Template name</Label>
                <input type="text" value={name}
                  onChange={(e) => setName(e.target.value.slice(0, 60))}
                  placeholder="e.g. Invoice Generator" maxLength={60}
                  style={inputStyle()} />
                <Counter value={name.length} max={60} />
              </div>

              {/* Category */}
              <div style={{ marginBottom: 14 }}>
                <Label>Category</Label>
                <select value={category} onChange={(e) => setCategory(e.target.value)}
                  style={inputStyle()}>
                  {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>

              {/* Description */}
              <div style={{ marginBottom: 14 }}>
                <Label>Description <span style={{ color: MUTED, fontWeight: 400, textTransform: "none", letterSpacing: 0 }}>(optional)</span></Label>
                <textarea value={description}
                  onChange={(e) => setDescription(e.target.value.slice(0, 200))}
                  placeholder="What does this template do?" rows={3}
                  maxLength={200}
                  style={{ ...inputStyle(), resize: "vertical", minHeight: 72, lineHeight: 1.5 }} />
                <Counter value={description.length} max={200} />
              </div>

              {/* Tags */}
              <div style={{ marginBottom: 14 }}>
                <Label>Tags <span style={{ color: MUTED, fontWeight: 400, textTransform: "none", letterSpacing: 0 }}>(comma separated)</span></Label>
                <input type="text" value={tagsText}
                  onChange={(e) => setTagsText(e.target.value)}
                  placeholder="invoice, business, finance"
                  style={inputStyle()} />
              </div>

              {/* Auth token */}
              <div style={{ marginBottom: 14 }}>
                <Label>Physis Bearer Token</Label>
                <input type="password" value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="Paste a Physis admin / signed-in session token"
                  style={inputStyle()} />
                <div style={{ fontSize: 11, color: MUTED, marginTop: 4 }}>
                  Cached in this browser as physis_admin_token after submit.
                </div>
              </div>

              {error && (
                <div style={{
                  marginTop: 4, marginBottom: 14, padding: "10px 14px",
                  background: "#FEE2E2", border: "1px solid #FCA5A5", borderRadius: 10,
                  fontSize: 13, color: "#991B1B", lineHeight: 1.5,
                }}>
                  {error}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        {!success && (
          <div style={{
            padding: "16px 26px 22px", borderTop: `1px solid ${BORDER}`, background: CARD_BG,
            display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap",
          }}>
            <button type="button" onClick={onClose} disabled={submitting} style={{
              background: CARD_BG, color: TEXT, border: `1px solid ${BORDER}`,
              borderRadius: 10, padding: "10px 18px", fontSize: 13, fontWeight: 600,
              cursor: submitting ? "not-allowed" : "pointer", fontFamily: INTER,
            }}>
              Cancel
            </button>
            <button type="button" onClick={handleSubmit} disabled={submitting} style={{
              background: GOLD, color: "#FFFFFF", border: "none",
              borderRadius: 10, padding: "11px 22px", fontSize: 14, fontWeight: 700,
              cursor: submitting ? "not-allowed" : "pointer", fontFamily: INTER,
              boxShadow: "0 2px 8px rgba(245, 158, 11, 0.30)",
              opacity: submitting ? 0.7 : 1,
            }}>
              {submitting ? "Submitting…" : "Promote to Template ⭐"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function Label({ children }) {
  return (
    <label style={{
      display: "block", fontSize: 11, fontWeight: 700, color: MUTED,
      letterSpacing: ".06em", textTransform: "uppercase", marginBottom: 6,
    }}>
      {children}
    </label>
  );
}

function Counter({ value, max }) {
  return (
    <div style={{ fontSize: 11, color: MUTED, marginTop: 4, textAlign: "right" }}>
      {value}/{max}
    </div>
  );
}

function ScoreBadge({ label, score, ok }) {
  return (
    <span style={{
      background: ok ? "#D1FAE5" : "#FEE2E2",
      color:      ok ? "#065F46" : "#991B1B",
      borderRadius: 999, padding: "4px 10px", fontSize: 11, fontWeight: 700,
    }}>
      {label}: {score}
    </span>
  );
}

function inputStyle() {
  return {
    width: "100%", boxSizing: "border-box",
    background: CARD_BG, color: TEXT, border: `1px solid ${BORDER}`,
    borderRadius: 10, padding: "10px 12px",
    fontSize: 14, fontFamily: INTER, outline: "none",
  };
}
