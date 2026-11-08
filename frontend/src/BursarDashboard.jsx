import { useMemo, useState } from "react";
import "./bursar-dashboard.css";

const money = (value, compact = false) => {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "KES —";
  if (compact && Math.abs(amount) >= 1_000_000) return `KES ${(amount / 1_000_000).toFixed(2)}M`;
  if (compact && Math.abs(amount) >= 100_000) return `KES ${(amount / 1_000).toFixed(0)}k`;
  return `KES ${amount.toLocaleString("en-KE", { maximumFractionDigits: 0 })}`;
};

const displayDate = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? String(value)
    : date.toLocaleString("en-KE", { dateStyle: "medium", timeStyle: "short" });
  };

const EMPTY_ARRAY = Object.freeze([]);

function Icon({ name, size = 18 }) {
  const paths = {
    wallet: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 9h18M7 15h4" /></>,
    balance: <><path d="M4 6h16v14H4zM4 10h16" /><path d="M8 3v3m8-3v3" /></>,
    alert: <><path d="M12 3 2.8 19h18.4L12 3Z" /><path d="M12 9v4m0 3h.01" /></>,
    today: <><path d="M12 3v18M17 7.5C17 5.6 14.8 4 12 4S7 5.6 7 7.5 9 10 12 11s5 1.6 5 3.5S14.8 18 12 18s-5-1.6-5-3.5" /></>,
    download: <><path d="M12 3v12m-5-5 5 5 5-5M5 20h14" /></>,
    search: <><circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 5 5" /></>,
    arrow: <><path d="M5 12h14m-6-6 6 6-6 6" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></>,
    receipt: <><path d="M7 3h7l5 5v13H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" /><path d="M14 3v6h5M9 14h6m-6 4h6" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">{paths[name] || paths.wallet}</svg>;
}

function Metric({ label, value, note, icon, tone, trend }) {
  return (
    <article className="bd-metric">
      <div className="bd-metric-top"><span>{label}</span><i className={`bd-icon bd-${tone}`}><Icon name={icon} size={16} /></i></div>
      <strong>{value}</strong>
      <div className="bd-metric-foot"><span>{note}</span>{trend ? <b>{trend}</b> : null}</div>
    </article>
  );
}

function TrendChart({ values }) {
  if (!Array.isArray(values) || values.length === 0) {
    return <div className="bd-empty"><strong>Collection trend not available yet</strong><span>The current dashboard API returns term totals and recent payments. A date-bucketed summary is needed to draw this chart with live values.</span></div>;
  }
  const max = Math.max(1, ...values.map((item) => Math.max(Number(item.target) || 0, Number(item.paid) || 0)));
  return (
    <div className="bd-chart" role="img" aria-label="Collected versus expected fees by period">
      {values.map((item) => {
        const paid = Math.max(0, Math.min(100, Number(item.paid) / max * 100));
        const target = Math.max(0, Math.min(100, Number(item.target) / max * 100));
        return (
          <div className="bd-chart-group" key={item.label}>
            <div className="bd-chart-bars">
              <i className="bd-bar-expected" style={{ height: `${target}%` }} title={`Expected ${item.label}: ${money(item.target)}`} />
              <i className="bd-bar-paid" style={{ height: `${paid}%` }} title={`Collected ${item.label}: ${money(item.paid)}`} />
            </div>
            <small>{item.label}</small>
          </div>
        );
      })}
    </div>
  );
}

export default function BursarDashboard({ me, data, onNavigate = () => {} }) {
  const [range, setRange] = useState("term");
  const [query, setQuery] = useState("");
  const fees = data?.fees || data?.summary || {};
  const payments = data?.payments || fees.recent_payments || EMPTY_ARRAY;
  const reportRows = data?.feeItems || data?.reportRows || [];
  const trends = data?.trendByPeriod?.[range] || data?.trend || [];
  const amountDue = Number(fees.amount_due);
  const amountPaid = Number(fees.amount_paid);
  const hasFeeSummary = Boolean(data?.fees || data?.summary);
  const collectionRate = !hasFeeSummary ? Number.NaN : Number.isFinite(Number(fees.collection_percentage))
    ? Number(fees.collection_percentage)
    : amountDue > 0 ? amountPaid / amountDue * 100 : Number.NaN;
  const filteredPayments = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return payments;
    return payments.filter((payment) => [
      payment.student_name, payment.student, payment.method, payment.reference,
    ].filter(Boolean).join(" ").toLowerCase().includes(needle));
  }, [payments, query]);
  const termLabel = data?.active_term?.name || data?.term?.name || "Current term";
  const schoolName = me?.school?.name || "School finance";

  if (me?.role && me.role !== "bursar") {
    return <section className="bd-page"><div className="bd-empty"><strong>Bursar dashboard</strong><span>This view is intended for the bursar role. Server-side fee permissions remain authoritative.</span></div></section>;
  }

  return (
    <section className="bd-page" aria-label="Bursar home dashboard">
      <header className="bd-heading">
        <div>
          <div className="bd-eyebrow"><span /> FINANCE OVERVIEW <i>/</i> {termLabel.toUpperCase()}</div>
          <h1>Good morning{me?.username ? `, ${me.username}` : ""}<em>.</em></h1>
          <p>{schoolName} · School fee collection and follow-up overview</p>
        </div>
        <div className="bd-heading-actions">
          <span className="bd-period"><Icon name="calendar" size={15} />{termLabel}</span>
          <button type="button" className="bd-primary" onClick={() => onNavigate("Fees")}>Record payment</button>
        </div>
      </header>

      {!data && <div className="bd-connection-note">Waiting for authorized fee summary data.</div>}
      <div className="bd-metrics">
        <Metric label="Collected this term" value={money(fees.amount_paid, true)} note="Received so far" icon="wallet" tone="green" trend={Number.isFinite(collectionRate) ? `${collectionRate.toFixed(1)}% collected` : null} />
        <Metric label="Outstanding balance" value={money(fees.balance, true)} note={`${fees.invoices ?? "—"} invoices in scope`} icon="balance" tone="amber" />
        <Metric label="Past due" value={money(fees.overdue_amount, true)} note={`${fees.overdue ?? "—"} overdue invoices`} icon="alert" tone="red" />
        <Metric label="Collected today" value={money(data?.today_collected)} note={data?.today_payment_count != null ? `${data.today_payment_count} payments today` : "Requires a daily payment aggregate"} icon="today" tone="blue" />
      </div>

      <div className="bd-primary-grid">
        <article className="bd-panel">
          <div className="bd-panel-heading"><div><h2>Collection trend</h2><p>Collected compared with expected fees</p></div><div className="bd-range" role="group" aria-label="Chart period">{["7d", "30d", "term"].map((item) => <button key={item} type="button" className={range === item ? "selected" : ""} onClick={() => setRange(item)}>{item === "term" ? "Term" : item}</button>)}</div></div>
          <div className="bd-legend"><span><i className="bd-key-paid" />Collected</span><span><i className="bd-key-target" />Expected</span>{Number.isFinite(collectionRate) && <b>{collectionRate.toFixed(1)}% of billed</b>}</div>
          <TrendChart values={trends} />
        </article>
        <article className="bd-panel">
          <div className="bd-panel-heading"><div><h2>Fee items</h2><p>Totals returned by the fee report</p></div><button type="button" className="bd-link" onClick={() => onNavigate("Fees")}>Open Fees <Icon name="arrow" size={13} /></button></div>
          {reportRows.length ? <div className="bd-fee-items">{reportRows.slice(0, 5).map((item) => <div className="bd-fee-row" key={item.fee_structure || item.name}><span><b>{item.name}</b><small>{item.invoices ?? 0} invoices</small></span><span><b>{money(item.paid ?? item.amount_paid)}</b><small>of {money(item.due ?? item.amount_due)}</small></span></div>)}</div> : <div className="bd-empty bd-empty-small"><strong>Fee item breakdown not loaded</strong><span>Pass the response from the existing fee report endpoint.</span></div>}
        </article>
      </div>

      <div className="bd-secondary-grid">
        <article className="bd-panel bd-payments-panel">
          <div className="bd-panel-heading"><div><h2>Recent payments</h2><p>Latest payments visible to this bursar</p></div><button type="button" className="bd-link" onClick={() => onNavigate("Fees")}>View all <Icon name="arrow" size={13} /></button></div>
          <label className="bd-search"><Icon name="search" size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search learner or reference" /></label>
          <div className="bd-table-wrap"><table className="bd-table"><thead><tr><th>Learner</th><th>Method</th><th>Reference</th><th>Date</th><th>Amount</th></tr></thead><tbody>
            {filteredPayments.slice(0, 6).map((payment, index) => <tr key={payment.id || payment.reference || index}><td>{payment.student_name || payment.student || "—"}</td><td>{payment.method || "—"}</td><td>{payment.reference || "—"}</td><td>{displayDate(payment.paid_at)}</td><td>{money(payment.amount)}</td></tr>)}
            {filteredPayments.length === 0 && <tr><td colSpan="5" className="bd-no-rows">No payments match this search.</td></tr>}
          </tbody></table></div>
          {payments.length === 0 && <p className="bd-table-note">The current dashboard API provides up to five recent payments when available.</p>}
        </article>
        <article className="bd-panel">
          <div className="bd-panel-heading"><div><h2>Arrears follow-up</h2><p>Outstanding balance aging</p></div><button type="button" className="bd-link" onClick={() => onNavigate("Fees")}>Open Fees <Icon name="arrow" size={13} /></button></div>
          {Array.isArray(data?.aging) && data.aging.length ? <div className="bd-aging">{data.aging.map((item) => <div className="bd-aging-row" key={item.label}><span>{item.label}</span><b>{money(item.amount)}</b><i><span style={{ width: `${Math.max(0, Math.min(100, Number(item.percent) || 0))}%` }} /></i></div>)}</div> : <div className="bd-empty bd-empty-small"><strong>Aging breakdown not available yet</strong><span>The current API returns total overdue amount, not aging buckets. No estimated buckets are shown.</span></div>}
          <div className="bd-attention"><Icon name="alert" size={16} /><span><b>{fees.overdue ?? "—"} overdue invoices</b><small>{money(fees.overdue_amount)} past the due date</small></span></div>
        </article>
      </div>
      <p className="bd-data-note">Amounts come from authorized school fee endpoints. Trend, category and aging visuals appear only when corresponding data is supplied.</p>
    </section>
  );
}
