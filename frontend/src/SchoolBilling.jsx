import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import "./platform-billing.css";

const money = (value) => `KES ${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const label = (value) => String(value || "—").replaceAll("_", " ");

export default function SchoolBilling({ go }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [capacity, setCapacity] = useState("");
  const [reason, setReason] = useState("");
  const [references, setReferences] = useState({});

  const load = useCallback(async () => {
    const response = await api("/api/billing/school/");
    const body = await response.json().catch(() => ({}));
    if (!response.ok) { setError(body.detail || "Could not load billing information."); return; }
    setData(body); setError("");
  }, []);
  useEffect(() => { void load(); }, [load]);

  const act = async (path, body, done) => {
    setBusy(true); setError(""); setSuccess("");
    const response = await api(path, "POST", body);
    const result = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) { setError(result.detail || "Request could not be completed."); return; }
    setSuccess(done(result)); await load();
  };

  if (!data && !error) return <div className="pb-loading">Loading Billing Centre…</div>;
  if (error && !data) return <section className="pb-wrap"><div className="pb-alert error">{error}</div><button className="pb-button" onClick={() => void load()}>Retry</button></section>;

  const progress = data.trial_progress;
  const statusText = {
    unconfigured: "Billing setup pending",
    trial_active: "Free trial · active",
    trial_completed: "Free trial · first examination cycle complete",
    subscription_active: "Subscription active",
    subscription_expired: "Subscription expired",
    licence_active: "Perpetual licence active",
    service_expired: "Licence active · cloud service renewal due",
    payment_pending: "Payment review pending",
    suspended: "Billing suspended",
  }[data.status] || label(data.status);

  return <main className="pb-wrap">
    <header className="pb-header"><div><span className="pb-eyebrow">SCHOOL ACCOUNT</span><h1>Billing Centre</h1><p>{data.school.name} · {data.active_academic_year ? `Active academic year: ${data.active_academic_year}` : "No active academic year detected"}</p></div><span className={`pb-pill ${data.status}`}>{statusText}</span></header>
    {error && <div className="pb-alert error" role="alert">{error}</div>}
    {success && <div className="pb-alert success" role="status">{success}</div>}

    <section className="pb-kpis">
      <article><small>Active enrolled students</small><strong>{Number(data.active_students).toLocaleString()}</strong><span>Distinct active learners in the latest active academic year</span></article>
      <article><small>Licensed capacity</small><strong>{data.licensed_capacity == null ? "Not set" : Number(data.licensed_capacity).toLocaleString()}</strong><span>{data.over_capacity ? "Current enrolment exceeds capacity — review required" : "Based on your current account"}</span></article>
      <article><small>Outstanding platform invoices</small><strong>{money(data.outstanding_kes)}</strong><span>Not the school’s learner fee invoices</span></article>
    </section>

    {progress && <section className="pb-card"><div className="pb-card-head"><div><span className="pb-eyebrow">GENUINE USAGE EVIDENCE</span><h2>First examination cycle</h2></div><span className={`pb-pill ${progress.complete ? "good" : "pending"}`}>{progress.complete ? "Complete" : "In progress"}</span></div>
      <p className="pb-muted">{progress.academic_year} · {progress.term} · {label(progress.assessment_type)} · {progress.classes_published}/{progress.classes_expected} classes published · {progress.analytics_generated}/{progress.classes_expected} analytics views · {progress.reports_generated}/{progress.reports_expected} report cards issued</p>
      <div className="pb-progress" role="progressbar" aria-valuenow={progress.reports_expected ? Math.min(100, Math.round(100 * progress.reports_generated / progress.reports_expected)) : 0} aria-valuemin="0" aria-valuemax="100"><span style={{ width: `${progress.reports_expected ? Math.min(100, Math.round(100 * progress.reports_generated / progress.reports_expected)) : 0}%` }} /></div>
      <div className="pb-cycle-grid">{(progress.classes || []).map((row) => <div key={row.class_level_id} className="pb-cycle-row"><b>Class {row.class_level_id}</b><span>{row.published ? "Published" : "Awaiting publication"}</span><span>{row.genuine_marks ? "Marks verified" : "Marks incomplete"}</span><span>{row.analytics ? "Analytics viewed" : "Analytics pending"}</span><span>{row.reports_generated}/{row.reports_expected} reports</span></div>)}</div>
      <small className="pb-muted">A trial has no calendar expiry. It completes only when each class in the recorded cycle has published genuine results, analytics have been generated, and archived report cards cover the eligible result cohort.</small>
    </section>}

    {data.status === "unconfigured" && <div className="pb-alert warning">This school existed before platform billing was configured. No trial or paid entitlement has been silently assigned. Contact the Marian Super Administrator to map the school’s account.</div>}
    {data.status === "trial_completed" && <div className="pb-alert warning">The first genuine examination cycle is complete. Starting another cycle requires a paid subscription or a supported Marian cloud licence. Historical academic records and archived reports are preserved.</div>}

    <section className="pb-card"><div className="pb-card-head"><div><span className="pb-eyebrow">SERVER-CALCULATED PRICES</span><h2>Plans and invoices</h2></div><span className="pb-muted">{data.pricing.currency} · VAT treatment: {label(data.pricing.vat_treatment)}</span></div>
      <div className="pb-plans">
        <article><span className="pb-eyebrow">TERM BY TERM</span><strong>{money(data.pricing.termly_kes)}</strong><p>Greater of the term minimum and the configured per-student term rate, using {data.active_students} active enrolled students.</p><button className="pb-button primary" disabled={busy || data.status === "unconfigured"} onClick={() => act("/api/billing/school/invoices/", { kind: "termly_subscription" }, (x) => `Invoice ${x.invoice_number} created. No payment was made.`)}>Request termly invoice</button></article>
        <article><span className="pb-eyebrow">ANNUAL SUBSCRIPTION</span><strong>{money(data.pricing.annual_kes)}</strong><p>{data.pricing.annual_discount_percent}% annual discount is applied to the configured termly rate.</p><button className="pb-button primary" disabled={busy || data.status === "unconfigured"} onClick={() => act("/api/billing/school/invoices/", { kind: "annual_subscription" }, (x) => `Invoice ${x.invoice_number} created. No payment was made.`)}>Request annual invoice</button></article>
        <article><span className="pb-eyebrow">CLOUD PERPETUAL LICENCE</span><strong>{money(data.pricing.perpetual_kes)}</strong><p>Upfront price based on the configured annual subscription multiplier. Cloud service renewal is separate and shown before purchase.</p><button className="pb-button" disabled={busy || data.status === "unconfigured"} onClick={() => act("/api/billing/school/invoices/", { kind: "perpetual_licence" }, (x) => `Invoice ${x.invoice_number} created. No payment was made.`)}>Request cloud licence invoice</button><small>Annual cloud service estimate after the first year: {money(data.pricing.cloud_service_annual_kes)}</small></article>
      </div>
      <div className="pb-alert info">Requesting an invoice does not charge you. Live M-Pesa/card gateways are not enabled. Bank-transfer references remain pending until a Super Administrator verifies settlement; this page cannot activate a subscription.</div>
    </section>

    {data.licensed_capacity != null && <section className="pb-card pb-capacity"><div><span className="pb-eyebrow">CAPACITY REVIEW</span><h2>Request more learner capacity</h2><p className="pb-muted">If active enrolment exceeds your recorded capacity, request a review. Approval does not charge or increase capacity; a priced invoice and verified payment are still required.</p></div><div className="pb-inline-form"><label>Requested capacity<input type="number" min={Math.max(data.active_students, (data.licensed_capacity || 0) + 1)} value={capacity} onChange={(e) => setCapacity(e.target.value)} placeholder="e.g. 500" /></label><label>Reason<input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} placeholder="Optional context" /></label><button className="pb-button" disabled={busy || !capacity} onClick={() => act("/api/billing/school/capacity-request/", { requested_capacity: Number(capacity), reason }, () => "Capacity request submitted for review. No charge has been made.")}>Send request</button></div></section>}

    <section className="pb-card"><div className="pb-card-head"><div><span className="pb-eyebrow">PLATFORM BILLING ONLY</span><h2>Invoices and payment status</h2></div></div>
      {data.invoices.length === 0 ? <p className="pb-muted">No platform invoices yet. Learner fee invoices are managed separately under Fees.</p> : <div className="pb-table-wrap"><table className="pb-table"><thead><tr><th>Invoice</th><th>Plan</th><th>Amount</th><th>Students / capacity</th><th>Status</th><th>Bank transfer reference</th><th>Action</th></tr></thead><tbody>{data.invoices.map((invoice) => <tr key={invoice.id}><td><b>{invoice.invoice_number}</b><small>{new Date(invoice.created_at).toLocaleDateString()}</small></td><td>{label(invoice.kind)}</td><td>{money(invoice.amount_kes)}</td><td>{invoice.active_student_snapshot} / {invoice.capacity_snapshot ?? "—"}</td><td><span className={`pb-pill ${invoice.status}`}>{label(invoice.status)}</span>{invoice.payments?.map((p) => <small key={p.id}>{label(p.method)} · {label(p.status)}{p.client_reference ? ` · ${p.client_reference}` : ""}</small>)}</td><td><input aria-label={`Bank reference for ${invoice.invoice_number}`} value={references[invoice.id] || ""} onChange={(e) => setReferences({ ...references, [invoice.id]: e.target.value })} placeholder="Bank transaction ref" /></td><td><button className="pb-button small" disabled={busy || invoice.status !== "outstanding" || !references[invoice.id]} onClick={() => act("/api/billing/school/bank-transfer/", { invoice_id: invoice.id, reference: references[invoice.id], idempotency_key: `bank-${invoice.id}-${references[invoice.id]}`.slice(0, 80) }, () => "Reference submitted. Access remains pending until settlement is verified.")}>Submit reference</button></td></tr>)}</tbody></table></div>}
      <div className="pb-alert info">Providing a reference is not evidence of cleared funds and does not activate service. Payment entries and decisions are audited.</div>
    </section>

    {data.over_capacity && <section className="pb-alert warning">Your active enrolled population is above the recorded capacity. No automatic charge has been made. Request an upgrade review above; Marian will provide the applicable price before any payment is requested.</section>}
    <section className="pb-card pb-hosting"><div><span className="pb-eyebrow">DEPLOYMENT OPTIONS</span><h2>School-hosted installation is a future option</h2></div><p>This archive does not include a supported installer, independent software-upgrade process, or school-only recovery path. For that reason, school-hosted perpetual licences are not issued as production-ready or activated from this centre. The school-hosted maintenance rate also remains unapproved until the platform owner confirms support and infrastructure terms.</p></section>
    <footer className="pb-foot">Platform subscription billing is separate from school fees billed to learners. For account mapping, invoice questions or access review, open <button className="pb-link" onClick={() => go?.("Help")}>Help</button>.</footer>
  </main>;
}
