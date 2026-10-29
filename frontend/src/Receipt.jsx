import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "./api";
import { Alert, Button, Loading } from "./ui";
import "./receipt.css";

const BASE = import.meta.env.VITE_API_URL || "";
const WIDTHS = [
  { key: "58", label: "58 mm" },
  { key: "80", label: "80 mm" },
  { key: "a4", label: "A4" },
];
const PAGE = {
  "58": "size:58mm auto;margin:2mm",
  "80": "size:80mm auto;margin:3mm",
  a4: "size:A4;margin:12mm",
};
const STATUS = { paid: "Paid in full", partial: "Part payment", waived: "Fee waived", pending: "Pending" };

const money = (n, cur) =>
  `${cur || "KES"} ${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const when = (v) => (v ? new Date(v).toLocaleString() : "");

function receiptText(d) {
  const s = d.school, f = d.fee, p = d.payment, cur = s.currency;
  const place = [s.location, s.sub_county, s.county].filter(Boolean).join(", ");
  const contact = [s.phone, s.email].filter(Boolean).join(" | ");
  const lines = [
    s.name, place || null, contact || null, "", "RECEIPT", d.receipt_number, "",
    `Student: ${d.student.name}`, `Admission no: ${d.student.admission_number}`,
    `Fee: ${f.name}`, `Academic year: ${f.academic_year}`,
    `Date: ${when(p.paid_at)}`, `Method: ${p.method_display}`,
    p.reference ? `Reference: ${p.reference}` : null,
    p.received_by ? `Received by: ${p.received_by}` : null, "",
    `AMOUNT PAID: ${money(p.amount, cur)}`,
    `Fee amount: ${money(f.amount_due, cur)}`,
    d.balances_verified ? `Previous balance: ${money(d.previous_balance, cur)}` : null,
    d.balances_verified ? `Balance after: ${money(d.balance_after, cur)}` : null,
    `Fee status: ${STATUS[f.status] || f.status}`, "",
    "Thank you for your payment.", `Quote ${d.receipt_number} to verify this receipt with the school.`,
  ];
  return lines.filter((x) => x !== null).join("\n");
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (e) {
    try {
      const t = document.createElement("textarea");
      t.value = text;
      t.style.position = "fixed";
      t.style.opacity = "0";
      document.body.appendChild(t);
      t.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(t);
      return ok;
    } catch (e2) {
      return false;
    }
  }
}

const Row = ({ k, v }) => (v ? <div className="rcpt-row"><dt>{k}</dt><dd>{v}</dd></div> : null);

export default function Receipt({ paymentId, onClose }) {
  const [state, setState] = useState({ loading: true });
  const [phase, setPhase] = useState("idle");
  const [width, setWidth] = useState(() => {
    try {
      const v = localStorage.getItem("rcpt-width");
      return ["58", "80", "a4"].includes(v) ? v : "80";
    } catch { return "80"; }
  });
  const [note, setNote] = useState("");
  const [tries, setTries] = useState(0);
  const [saving, setSaving] = useState(false);
  const timers = useRef([]);
  const running = useRef(false);
  const auto = useRef(false);
  const runRef = useRef(null);
  const closeRef = useRef(onClose);

  useEffect(() => { closeRef.current = onClose; });

  useEffect(() => {
    let alive = true;
    auto.current = false;
    setState({ loading: true });
    (async () => {
      try {
        const r = await api(`/api/fees/payments/${paymentId}/receipt/`);
        if (!alive) return;
        if (r.ok) setState({ data: await r.json() });
        else if (r.status === 403) setState({ error: "You do not have permission to view this receipt." });
        else if (r.status === 404) setState({ error: "Receipt not found." });
        else setState({ error: "Could not load the receipt. Please try again." });
      } catch (e) {
        if (alive) setState({ error: "Network problem. Check your connection and try again." });
      }
    })();
    return () => { alive = false; };
  }, [paymentId, tries]);

  useEffect(() => {
    document.body.classList.add("rcpt-open");
    const key = (e) => { if (e.key === "Escape") closeRef.current(); };
    window.addEventListener("keydown", key);
    const pending = timers.current;
    return () => {
      document.body.classList.remove("rcpt-open");
      window.removeEventListener("keydown", key);
      pending.forEach(clearTimeout);
    };
  }, []);

  const run = () => {
    if (running.current || !state.data) return;
    running.current = true;
    timers.current.forEach(clearTimeout);
    timers.current = [];
    setNote("");
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setPhase("ready");
      running.current = false;
      return;
    }
    setPhase("printing");
    timers.current.push(setTimeout(() => setPhase("cut"), 2000));
    timers.current.push(setTimeout(() => { setPhase("ready"); running.current = false; }, 2600));
  };

  const tear = () => {
    if (phase !== "ready") return;
    timers.current.forEach(clearTimeout);
    timers.current = [];
    setNote("");
    setPhase("tearing");
    timers.current.push(setTimeout(() => setPhase("torn"), 800));
  };

  useEffect(() => { runRef.current = run; });

  useEffect(() => {
    if (!state.data || auto.current) return;
    auto.current = true;
    timers.current.push(setTimeout(() => { if (runRef.current) runRef.current(); }, 200));
  }, [state.data]);

  const openDialog = (msg) => {
    setNote(msg);
    timers.current.push(setTimeout(() => window.print(), 60));
  };

  const download = async () => {
    if (saving) return;
    setSaving(true);
    setNote("");
    try {
      const r = await api("/api/documents/fee-receipts/", "POST", { payment_ids: [paymentId], format: "combined" });
      if (!r.ok) { setNote("Could not create the PDF. Please try again."); return; }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `receipt-${state.data.receipt_number}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      setNote("PDF created. Check your downloads.");
    } catch {
      setNote("Could not create the PDF. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const copy = async () => {
    const ok = await copyText(receiptText(state.data));
    setNote(ok ? "Receipt details copied." : "Could not copy. Please select and copy the text manually.");
  };

  const d = state.data;
  const working = phase === "printing" || phase === "cut";
  const paperCls = `rcpt-paper ${phase === "idle" || phase === "torn" ? "rcpt-paper-idle" : phase === "printing" ? "rcpt-feeding" : phase === "cut" ? "rcpt-cut" : phase === "tearing" ? "rcpt-tear" : ""}`;
  const statusText = phase === "idle" ? "Ready. Press Print receipt."
    : phase === "printing" ? "Printing..."
    : phase === "cut" ? "Cutting..."
    : phase === "tearing" ? "Tearing..."
    : phase === "torn" ? "Receipt cut and torn. Ready to print a fresh copy anytime."
    : note || "Receipt ready.";
  const logo = d && d.school.logo ? (d.school.logo.startsWith("/") ? BASE + d.school.logo : d.school.logo) : "";

  return createPortal(
    <div className={`rcpt-portal rcpt-w${width}`} onClick={onClose}>
      <style>{`@media print{@page{${PAGE[width]}}}`}</style>
      <div className="rcpt-dialog" role="dialog" aria-modal="true" aria-label="Fee receipt" onClick={(e) => e.stopPropagation()}>
        <div className="rcpt-top rcpt-noprint">
          <h3>Fee receipt</h3>
          <Button size="sm" kind="ghost" onClick={onClose} aria-label="Close receipt">Close</Button>
        </div>
        {state.loading && <div className="rcpt-noprint"><Loading /></div>}
        {state.error && (
          <div className="rcpt-noprint">
            <Alert kind="err">{state.error}</Alert>
            <div className="rcpt-actions"><Button kind="secondary" onClick={() => setTries((t) => t + 1)}>Try again</Button></div>
          </div>
        )}
        {d && (
          <>
            <div className={`rcpt-printer ${working ? "rcpt-on" : ""}`} aria-hidden="true"><i className="rcpt-led" /><span className="rcpt-mouth" /></div>
            <div className={`rcpt-slot ${phase === "idle" ? "rcpt-slot-idle" : ""}`}>
              {(phase === "idle" || phase === "torn") && <p className="rcpt-empty rcpt-noprint">{phase === "torn" ? "Receipt cut and torn." : "No receipt printed yet."}</p>}
              <article className={paperCls} aria-label={`Receipt ${d.receipt_number}`}>
                <header className="rcpt-head">
                  {logo && <img className="rcpt-logo" src={logo} alt="" onError={(e) => { e.currentTarget.style.display = "none"; }} />}
                  <b className="rcpt-school">{d.school.name}</b>
                  {d.school.motto && <small>{d.school.motto}</small>}
                  {[d.school.location, d.school.sub_county, d.school.county].filter(Boolean).length > 0 && (
                    <small>{[d.school.location, d.school.sub_county, d.school.county].filter(Boolean).join(", ")}</small>
                  )}
                  {(d.school.phone || d.school.email) && <small>{[d.school.phone, d.school.email].filter(Boolean).join(" | ")}</small>}
                </header>
                <h4 className="rcpt-title">RECEIPT</h4>
                <p className="rcpt-no">{d.receipt_number}</p>
          <div className={`rcpt-stamp ${phase === "idle" || phase === "printing" ? "rcpt-stamp-wait" : ""}`} aria-hidden="true"><b>PAYMENT RECEIVED</b><small>{when(d.payment.paid_at)}</small></div>
                <dl className="rcpt-rows">
                  <Row k="Student" v={d.student.name} />
                  <Row k="Admission no" v={d.student.admission_number} />
                  <Row k="Fee" v={d.fee.name} />
                  <Row k="Academic year" v={d.fee.academic_year} />
                  <Row k="Date" v={when(d.payment.paid_at)} />
                  <Row k="Method" v={d.payment.method_display} />
                  <Row k="Reference" v={d.payment.reference} />
                  <Row k="Received by" v={d.payment.received_by} />
                  <Row k="Notes" v={d.payment.notes} />
                </dl>
                <div className="rcpt-total"><span>AMOUNT PAID</span><b>{money(d.payment.amount, d.school.currency)}</b></div>
                <dl className="rcpt-rows">
                  <Row k="Fee amount" v={money(d.fee.amount_due, d.school.currency)} />
          <Row k="Category" v={d.fee.category === "boarder" ? "Boarder" : d.fee.category === "day" ? "Day scholar" : ""} />
          <Row k="Balance brought forward" v={money(d.fee.balance_brought_forward, d.school.currency)} />
                  {d.balances_verified && <Row k="Previous balance" v={money(d.previous_balance, d.school.currency)} />}
                  {d.balances_verified && <Row k="Balance after" v={money(d.balance_after, d.school.currency)} />}
                  <Row k="Fee status" v={STATUS[d.fee.status] || d.fee.status} />
                </dl>
                <footer className="rcpt-foot">
                  <p>Thank you for your payment.</p>
                  <small>Quote {d.receipt_number} to verify this receipt with the school.</small>
                </footer>
              </article>
            </div>
            <p className="rcpt-status rcpt-noprint" role="status" aria-live="polite">{statusText}</p>
            {!d.balances_verified && d.fee.status !== "waived" && (
              <p className="rcpt-hint rcpt-noprint">Balance lines are hidden because this fee's payment records do not add up. Please review the fee.</p>
            )}
            <div className="rcpt-widths rcpt-noprint" role="group" aria-label="Paper width">
              {WIDTHS.map((w) => (
                <button key={w.key} type="button" className={`rcpt-chip ${width === w.key ? "on" : ""}`} aria-pressed={width === w.key} onClick={() => { setWidth(w.key); try { localStorage.setItem("rcpt-width", w.key); } catch { /* storage unavailable */ } }}>{w.label}</button>
              ))}
            </div>
            <div className="rcpt-actions rcpt-noprint">
              {(phase === "idle" || phase === "torn") && <Button kind="teal" onClick={run}>Print receipt</Button>}
              {working && <Button kind="teal" busy disabled>Printing...</Button>}
              {phase === "ready" && (
                <>
                  <Button kind="teal" onClick={() => openDialog("Print dialog opened. Check your printer to confirm it printed.")}>Open print dialog</Button>
                  <Button kind="secondary" onClick={run}>Print again</Button>
            <Button kind="secondary" onClick={tear}>Tear receipt</Button>
                  <Button kind='secondary' busy={saving} disabled={saving} onClick={download}>Download PDF</Button>
                </>
              )}
              <Button kind="secondary" onClick={copy}>Copy details</Button>
            </div>
          </>
        )}
      </div>
    </div>,
    document.body
  );
}
