import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import "./platform-billing.css";

const money = (value) => `KES ${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const label = (value) => String(value || "—").replaceAll("_", " ");
const statusOptions = ["unconfigured", "trial_active", "trial_completed", "payment_pending", "subscription_active", "subscription_expired", "licence_active", "service_expired", "suspended"];

export default function PlatformBilling() {
  const [data, setData] = useState(null), [pricing, setPricing] = useState(null), [audit, setAudit] = useState([]);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [success, setSuccess] = useState("");
  const [selectedSchool, setSelectedSchool] = useState(""), [kind, setKind] = useState("termly_subscription"), [capacity, setCapacity] = useState("");
  const [search, setSearch] = useState(""), [drafts, setDrafts] = useState({}), [note, setNote] = useState("");

  const load = useCallback(async () => {
    const [overview, prices, logs] = await Promise.all([
      api(`/api/billing/admin/overview/${search ? `?q=${encodeURIComponent(search)}` : ""}`),
      api("/api/billing/admin/pricing/"), api("/api/billing/admin/audit/"),
    ]);
    const [o, p, a] = await Promise.all([overview.json().catch(() => ({})), prices.json().catch(() => ({})), logs.json().catch(() => [])]);
    if (!overview.ok || !prices.ok) { setError(o.detail || p.detail || "Only the Super Administrator may open this platform billing centre."); return; }
    setData(o); setPricing(p); setAudit(Array.isArray(a) ? a : []); setError("");
  }, [search]);
  useEffect(() => { void load(); }, [load]);

  const post = async (path, body, message) => {
    setBusy(true); setError(""); setSuccess("");
    const response = await api(path, "POST", body); const result = await response.json().catch(() => ({})); setBusy(false);
    if (!response.ok) { setError(result.detail || "Request failed."); return; }
    setSuccess(message || result.detail || "Saved."); await load();
  };
  const savePrices = async () => {
    setBusy(true); setError(""); setSuccess("");
    const payload = { ...pricing,
      term_minimum_kes: pricing.term_minimum_kes,
      per_student_term_kes: pricing.per_student_term_kes,
      annual_discount_percent: pricing.annual_discount_percent,
      terms_per_year: Number(pricing.terms_per_year),
      perpetual_annual_multiplier: Number(pricing.perpetual_annual_multiplier),
      cloud_service_percent: pricing.cloud_service_percent,
      school_hosted_maintenance_percent: pricing.school_hosted_maintenance_percent === "" ? null : pricing.school_hosted_maintenance_percent,
    };
    const response = await api("/api/billing/admin/pricing/", "PATCH", payload); const result = await response.json().catch(() => ({})); setBusy(false);
    if (!response.ok) { setError(result.detail || "Could not save pricing."); return; }
    setPricing(result); setSuccess("Pricing configuration saved and audited."); await load();
  };
  const updateStatus = (school, status) => {
    const current = drafts[school.school_id] || { status: school.status, access_type: school.access_type, licensed_capacity: school.licensed_capacity ?? "" };
    return setDrafts({ ...drafts, [school.school_id]: { ...current, status } });
  };
  const saveStatus = async (school) => {
    const d = drafts[school.school_id] || { status: school.status, access_type: school.access_type, licensed_capacity: school.licensed_capacity };
    await post(`/api/billing/admin/schools/${school.school_id}/profile/`, {
      status: d.status, access_type: d.access_type,
      licensed_capacity: d.licensed_capacity === "" ? null : Number(d.licensed_capacity), note,
    }, `Billing profile updated for ${school.school_name}.`);
  };
  if (!data && !error) return <div className="pb-loading">Loading platform billing…</div>;
  if (error && !data) return <main className="pb-wrap"><div className="pb-alert error">{error}</div></main>;
  const s = data.summary;

  return <main className="pb-wrap">
    <header className="pb-header"><div><span className="pb-eyebrow">PLATFORM OWNER · SUPER ADMINISTRATOR ONLY</span><h1>Platform Billing</h1><p>Subscription, licensing, invoices, payment review, trial evidence and audit history. This does not manage learner fee accounts.</p></div><span className="pb-pill pending">Live providers disabled</span></header>
    {error && <div className="pb-alert error" role="alert">{error}</div>}{success && <div className="pb-alert success" role="status">{success}</div>}
    <div className="pb-alert warning"><b>Payment readiness:</b> M-Pesa, card and gateway settlement are not live. No provider approval or credentials are present. Bank transfers remain manual and access is activated only after a recorded Super Administrator verification. This dashboard never represents an unverified reference as a payment.</div>

    <section className="pb-kpis pb-kpis-wide">
      {[["Registered schools", s.registered_schools], ["Active trials", s.trials_active], ["Trials awaiting full cycle", s.trials_awaiting_completion], ["Completed trials", s.trials_completed], ["Active subscriptions", s.active_subscriptions], ["Perpetual licences", s.perpetual_licences], ["Pending payments", s.pending_payments], ["Outstanding invoices", s.outstanding_invoices], ["Upcoming renewals · 30d", s.upcoming_renewals], ["Over-capacity schools", s.over_capacity_schools], ["Verified payments", money(s.successful_kes)], ["Outstanding balance", money(s.outstanding_kes)].map((x) => x)].map(([name, value]) => <article key={name}><small>{name}</small><strong>{value ?? 0}</strong></article>)}
    </section>

    <section className="pb-card"><div className="pb-card-head"><div><span className="pb-eyebrow">CENTRAL CONFIGURATION</span><h2>Pricing and unresolved commercial policy</h2></div><button className="pb-button primary" onClick={savePrices} disabled={busy}>Save configuration</button></div>
      {pricing && <>
        <div className="pb-form-grid">
          <label>Term minimum · KES<input type="number" min="0" step="0.01" value={pricing.term_minimum_kes} onChange={(e) => setPricing({ ...pricing, term_minimum_kes: e.target.value })} /></label>
          <label>Per student per term · KES<input type="number" min="0" step="0.01" value={pricing.per_student_term_kes} onChange={(e) => setPricing({ ...pricing, per_student_term_kes: e.target.value })} /></label>
          <label>Terms per year<input type="number" min="1" max="4" value={pricing.terms_per_year} onChange={(e) => setPricing({ ...pricing, terms_per_year: e.target.value })} /></label>
          <label>Annual discount · %<input type="number" min="0" max="100" step="0.01" value={pricing.annual_discount_percent} onChange={(e) => setPricing({ ...pricing, annual_discount_percent: e.target.value })} /></label>
          <label>Perpetual multiplier · years<input type="number" min="1" max="20" value={pricing.perpetual_annual_multiplier} onChange={(e) => setPricing({ ...pricing, perpetual_annual_multiplier: e.target.value })} /></label>
          <label>Annual cloud-service rate · %<input type="number" min="0" max="100" step="0.01" value={pricing.cloud_service_percent} onChange={(e) => setPricing({ ...pricing, cloud_service_percent: e.target.value })} /></label>
          <label>School-hosted maintenance · % (unapproved)<input type="number" min="0" max="100" step="0.01" value={pricing.school_hosted_maintenance_percent ?? ""} onChange={(e) => setPricing({ ...pricing, school_hosted_maintenance_percent: e.target.value })} placeholder="Not set" /></label>
          <label>VAT treatment<select value={pricing.vat_treatment} onChange={(e) => setPricing({ ...pricing, vat_treatment: e.target.value })}><option value="undecided">Undecided</option><option value="inclusive">Inclusive</option><option value="exclusive">Exclusive</option></select></label>
          <label>Post-expiry examination policy<select value={pricing.post_expiry_policy} onChange={(e) => setPricing({ ...pricing, post_expiry_policy: e.target.value })}><option value="unrestricted">Unrestricted exam writes (current; pending approval)</option><option value="read_only_history">Block exam-cycle/mark writes; preserve historical reads</option><option value="support_only">Block exam writes; support-assisted renewal</option></select></label>
          <label className="pb-check"><input type="checkbox" checked={!!pricing.school_hosted_maintenance_approved} onChange={(e) => setPricing({ ...pricing, school_hosted_maintenance_approved: e.target.checked })} /> Approve school-hosted maintenance rate</label>
          <label className="pb-check"><input type="checkbox" checked={!!pricing.post_expiry_policy_approved} onChange={(e) => setPricing({ ...pricing, post_expiry_policy_approved: e.target.checked })} /> Approve selected post-expiry restriction</label>
        </div>
        <div className="pb-alert info">Current defaults are configurable commercial assumptions, not legal, tax or provider-approved terms. VAT stays “undecided” until confirmed. School-hosted maintenance cannot be invoiced unless the rate is explicitly approved.</div>
      </>}
    </section>

    <section className="pb-card"><div className="pb-card-head"><div><span className="pb-eyebrow">ISSUE A SCHOOL INVOICE</span><h2>Manual invoice creation</h2></div></div>
      <div className="pb-inline-form"><label>School<select value={selectedSchool} onChange={(e) => setSelectedSchool(e.target.value)}><option value="">Select a school…</option>{data.schools.map((school) => <option key={school.school_id} value={school.school_id}>{school.school_name} · {school.active_students} active</option>)}</select></label><label>Invoice type<select value={kind} onChange={(e) => setKind(e.target.value)}><option value="termly_subscription">Termly subscription</option><option value="annual_subscription">Annual subscription</option><option value="perpetual_licence">Cloud perpetual licence</option><option value="cloud_service">Cloud service renewal</option><option value="school_maintenance">School-hosted maintenance (approved only)</option></select></label><label>Billable capacity<input type="number" min="1" value={capacity} onChange={(e) => setCapacity(e.target.value)} placeholder="Uses active/recorded capacity" /></label><button className="pb-button primary" disabled={busy || !selectedSchool} onClick={() => post("/api/billing/admin/invoices/", { school_id: Number(selectedSchool), kind, capacity: capacity ? Number(capacity) : undefined }, "Invoice created. No payment was initiated.")}>Create invoice</button></div>
    </section>

    <section className="pb-card"><div className="pb-card-head"><div><span className="pb-eyebrow">TENANT ACCOUNTS</span><h2>School billing status and trial evidence</h2></div><input className="pb-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search school or code" /></div>
      <div className="pb-table-wrap"><table className="pb-table"><thead><tr><th>School</th><th>Status / access</th><th>Active students / cap</th><th>Trial progress</th><th>Over capacity</th><th>Manual action</th></tr></thead><tbody>{data.schools.map((school) => { const d = drafts[school.school_id] || { status: school.status, access_type: school.access_type, licensed_capacity: school.licensed_capacity ?? "" }; const p = school.trial_progress; return <tr key={school.school_id}><td><b>{school.school_name}</b><small>{school.code} · {school.active_academic_year || "no active year"}</small></td><td><span className={`pb-pill ${school.status}`}>{label(school.status)}</span><small>{label(school.access_type)}</small></td><td>{school.active_students} / {school.licensed_capacity ?? "—"}</td><td>{p ? <small>{p.classes_published}/{p.classes_expected} published · {p.analytics_generated}/{p.classes_expected} analytics · {p.reports_generated}/{p.reports_expected} reports</small> : <small>No cycle started</small>}</td><td>{school.over_capacity ? <span className="pb-pill warning">Yes</span> : "No"}</td><td><select value={d.status} onChange={(e) => updateStatus(school, e.target.value)} aria-label={`Status for ${school.school_name}`}>{statusOptions.map((v) => <option key={v} value={v}>{label(v)}</option>)}</select><select value={d.access_type} onChange={(e) => setDrafts({ ...drafts, [school.school_id]: { ...d, access_type: e.target.value } })} aria-label={`Access type for ${school.school_name}`}><option value="trial">Trial</option><option value="subscription">Subscription</option><option value="perpetual">Perpetual</option></select><input aria-label={`Capacity for ${school.school_name}`} type="number" min="1" value={d.licensed_capacity} onChange={(e) => setDrafts({ ...drafts, [school.school_id]: { ...d, licensed_capacity: e.target.value } })} placeholder="Capacity"/><button className="pb-button small" disabled={busy} onClick={() => saveStatus(school)}>Save audited status</button><button className="pb-button small" onClick={() => setSelectedSchool(String(school.school_id))}>Select for invoice</button></td></tr>; })}</tbody></table></div>
      <label className="pb-note">Audit note for manual status changes<input value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder="Reason / support case reference" /></label>
    </section>

    <section className="pb-card"><div className="pb-card-head"><div><span className="pb-eyebrow">SETTLEMENT CONTROL</span><h2>Pending bank-transfer submissions</h2></div></div>
      {data.pending_payments.length === 0 ? <p className="pb-muted">No pending payment submissions.</p> : <div className="pb-table-wrap"><table className="pb-table"><thead><tr><th>School / invoice</th><th>Amount</th><th>Reference</th><th>Submitted</th><th>Review decision</th></tr></thead><tbody>{data.pending_payments.map((p) => <tr key={p.id}><td>{p.invoice__school__name}<small>{p.invoice__invoice_number} · {label(p.method)}</small></td><td>{money(p.amount_kes)}</td><td>{p.client_reference || "—"}</td><td>{new Date(p.created_at).toLocaleString()}</td><td><button className="pb-button small primary" disabled={busy} onClick={() => post(`/api/billing/admin/payments/${p.id}/review/`, { action: "verify", provider_transaction_id: p.client_reference, note }, "Payment verified; invoice entitlement activated.")}>Verify settled funds</button><button className="pb-button small danger" disabled={busy} onClick={() => post(`/api/billing/admin/payments/${p.id}/review/`, { action: "fail", note }, "Payment marked failed.")}>Mark failed</button></td></tr>)}</tbody></table></div>}
      <small className="pb-muted">Verify only against cleared funds in the official bank statement. A school-entered transfer reference is not proof of settlement.</small>
    </section>

    <section className="pb-card"><div className="pb-card-head"><div><span className="pb-eyebrow">CAPACITY WORKFLOW</span><h2>Pending upgrade requests</h2></div></div>
      {data.capacity_requests.length === 0 ? <p className="pb-muted">No capacity requests awaiting review.</p> : <div className="pb-table-wrap"><table className="pb-table"><thead><tr><th>School</th><th>Current cap</th><th>Active students at request</th><th>Requested cap</th><th>Reason</th><th>Decision</th></tr></thead><tbody>{data.capacity_requests.map((r) => <tr key={r.id}><td>{r.school__name}</td><td>{r.current_capacity ?? "—"}</td><td>{r.active_students_snapshot}</td><td>{r.requested_capacity}</td><td>{r.reason || "—"}</td><td><button className="pb-button small primary" onClick={() => post(`/api/billing/admin/capacity-requests/${r.id}/decision/`, { action: "approve", note }, "Capacity approved for purchase; no charge or capacity change has occurred.")}>Approve review</button><button className="pb-button small danger" onClick={() => post(`/api/billing/admin/capacity-requests/${r.id}/decision/`, { action: "reject", note }, "Capacity request rejected.")}>Reject</button></td></tr>)}</tbody></table></div>}
    </section>

    <section className="pb-card"><div className="pb-card-head"><div><span className="pb-eyebrow">ACCOUNTING TRAIL</span><h2>Recent platform billing audit</h2></div></div>
      {audit.length === 0 ? <p className="pb-muted">No platform billing actions recorded yet.</p> : <div className="pb-table-wrap"><table className="pb-table"><thead><tr><th>Time</th><th>School</th><th>Actor</th><th>Action</th><th>Record</th></tr></thead><tbody>{audit.slice(0, 80).map((a) => <tr key={a.id}><td>{new Date(a.created_at).toLocaleString()}</td><td>{a.school__name || "Platform"}</td><td>{a.actor__username || "System / signed callback"}</td><td>{label(a.action)}</td><td><small>{a.object_type} {a.object_id} {a.details?.invoice ? `· ${a.details.invoice}` : ""}</small></td></tr>)}</tbody></table></div>}
    </section>
    <section className="pb-card pb-hosting"><h2>School-hosted licensing readiness</h2><p>Only Marian cloud perpetual licences can currently be invoiced and activated. This archive does not provide a supported installer, separate upgrade channel, or school-only backup/recovery runbook. The API refuses school-hosted licence invoices; no UI claims that option is production-ready. The annual maintenance rate remains unapproved unless explicitly approved above after owner review.</p></section>
  </main>;
}
