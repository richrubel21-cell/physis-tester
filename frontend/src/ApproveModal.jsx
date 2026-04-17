import { useState } from "react";

const PHYSIS_API = import.meta.env.VITE_API_BASE || "https://physis.onrender.com";

const CATEGORY_OPTIONS = ["Generators", "Analyzers", "Trackers", "Assistants", "Transformers"];

const input = {
  width: "100%",
  boxSizing: "border-box",
  background: "#11111b",
  border: "1px solid #313244",
  borderRadius: "8px",
  color: "#cdd6f4",
  padding: "10px 12px",
  fontSize: "13px",
  fontFamily: "inherit",
  outline: "none",
};

const label = {
  display: "block",
  color: "#a6adc8",
  fontSize: "11px",
  fontWeight: "600",
  marginBottom: "6px",
  textTransform: "uppercase",
  letterSpacing: "0.08em",
};

export default function ApproveModal({ run, onClose }) {
  const [name, setName]               = useState(run?.description?.slice(0, 60) || "");
  const [tagline, setTagline]         = useState("");
  const [description, setDescription] = useState(run?.description || "");
  const [category, setCategory]       = useState(CATEGORY_OPTIONS[0]);
  const [tagsText, setTagsText]       = useState("");
  const [featured, setFeatured]       = useState(false);
  const [submitting, setSubmitting]   = useState(false);
  const [success, setSuccess]         = useState(false);
  const [error, setError]             = useState("");
  const [token, setToken]             = useState(() => localStorage.getItem("physis_admin_token") || "");

  async function handleSubmit() {
    setError("");
    if (!name.trim() || !tagline.trim() || !description.trim()) {
      setError("Name, tagline, and description are required.");
      return;
    }
    if (tagline.length > 80) {
      setError("Tagline must be 80 characters or fewer.");
      return;
    }
    if (description.length > 300) {
      setError("Description must be 300 characters or fewer.");
      return;
    }
    if (!token.trim()) {
      setError("Paste a Physis admin Bearer token to authorize this submission.");
      return;
    }

    localStorage.setItem("physis_admin_token", token.trim());
    setSubmitting(true);
    try {
      // Extract subdomain from live_url if present: https://foo.myphysis.ai → 'foo'
      let subdomain = null;
      try {
        if (run?.live_url) {
          const host = new URL(run.live_url).hostname;
          subdomain = host.split(".")[0] || null;
        }
      } catch { /* ignore */ }

      const res = await fetch(`${PHYSIS_API}/api/marketplace/apps/create`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token.trim()}`,
        },
        body: JSON.stringify({
          name:        name.trim(),
          tagline:     tagline.trim(),
          description: description.trim(),
          category,
          tags:        tagsText.split(",").map(t => t.trim()).filter(Boolean),
          featured,
          subdomain,
          template_id: run?.template_id || null,
          build_id:    run?.build_id || run?.run_id || null,
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
    <div style={{
      position: "fixed", inset: 0,
      background: "rgba(0,0,0,0.7)", backdropFilter: "blur(4px)",
      zIndex: 500, display: "flex", alignItems: "center", justifyContent: "center", padding: "24px",
    }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{
        width: "100%", maxWidth: "540px", maxHeight: "92vh", overflowY: "auto",
        background: "#1e1e2e", border: "1px solid #313244", borderRadius: "14px",
        padding: "24px 26px", fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "14px" }}>
          <h2 style={{ color: "#cdd6f4", fontSize: "18px", margin: 0 }}>✓ Approve App for Marketplace</h2>
          <button type="button" onClick={onClose} style={{ background: "none", border: "none", color: "#6c7086", fontSize: "22px", cursor: "pointer" }}>×</button>
        </div>

        {success ? (
          <div style={{ padding: "40px 8px", textAlign: "center" }}>
            <div style={{ fontSize: "48px", marginBottom: "14px" }}>🎉</div>
            <div style={{ color: "#a6e3a1", fontSize: "16px", fontWeight: "700", marginBottom: "8px" }}>
              App added to marketplace!
            </div>
            <div style={{ color: "#6c7086", fontSize: "13px" }}>You can close this modal now.</div>
          </div>
        ) : (
          <>
            <div style={{ marginBottom: "14px" }}>
              <label style={label}>App Name</label>
              <input type="text" style={input} value={name} onChange={e => setName(e.target.value)} maxLength={80} />
            </div>
            <div style={{ marginBottom: "14px" }}>
              <label style={label}>Tagline (max 80)</label>
              <input type="text" style={input} value={tagline} onChange={e => setTagline(e.target.value)} maxLength={80} placeholder="One-sentence pitch" />
              <div style={{ color: "#6c7086", fontSize: "10px", marginTop: "4px" }}>{tagline.length}/80</div>
            </div>
            <div style={{ marginBottom: "14px" }}>
              <label style={label}>Description (max 300)</label>
              <textarea rows={3} style={{ ...input, resize: "vertical" }} value={description} onChange={e => setDescription(e.target.value)} maxLength={300} />
              <div style={{ color: "#6c7086", fontSize: "10px", marginTop: "4px" }}>{description.length}/300</div>
            </div>
            <div style={{ marginBottom: "14px" }}>
              <label style={label}>Category</label>
              <select style={input} value={category} onChange={e => setCategory(e.target.value)}>
                {CATEGORY_OPTIONS.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div style={{ marginBottom: "14px" }}>
              <label style={label}>Tags (comma separated)</label>
              <input type="text" style={input} value={tagsText} onChange={e => setTagsText(e.target.value)} placeholder="writing, ai, productivity" />
            </div>
            <div style={{ marginBottom: "14px", display: "flex", alignItems: "center", gap: "10px" }}>
              <input type="checkbox" id="app-featured" checked={featured} onChange={e => setFeatured(e.target.checked)} />
              <label htmlFor="app-featured" style={{ color: "#cdd6f4", fontSize: "13px", cursor: "pointer" }}>Featured app</label>
            </div>
            <div style={{ marginBottom: "18px" }}>
              <label style={label}>Physis Admin Bearer Token</label>
              <input type="password" style={input} value={token} onChange={e => setToken(e.target.value)} placeholder="Bearer token from Physis Supabase admin session" />
              <div style={{ color: "#6c7086", fontSize: "10px", marginTop: "4px" }}>
                Stored in localStorage so you only paste it once per machine.
              </div>
            </div>

            {error && (
              <div style={{ background: "#3a1e1e", border: "1px solid #f38ba8", color: "#f38ba8", borderRadius: "8px", padding: "10px 12px", fontSize: "12px", marginBottom: "14px" }}>
                {error}
              </div>
            )}

            <div style={{ display: "flex", gap: "10px" }}>
              <button type="button" onClick={onClose} disabled={submitting} style={{ flex: 1, background: "transparent", color: "#6c7086", border: "1px solid #313244", borderRadius: "8px", padding: "10px", fontSize: "13px", fontWeight: "600", cursor: submitting ? "not-allowed" : "pointer" }}>
                Cancel
              </button>
              <button type="button" onClick={handleSubmit} disabled={submitting} style={{ flex: 2, background: submitting ? "#44385a" : "#7c3aed", color: "white", border: "none", borderRadius: "8px", padding: "10px", fontSize: "13px", fontWeight: "700", cursor: submitting ? "not-allowed" : "pointer" }}>
                {submitting ? "Submitting..." : "Approve for Marketplace"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
