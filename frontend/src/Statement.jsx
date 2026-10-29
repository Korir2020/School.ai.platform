import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "./api";
import { Alert, Button, Loading } from "./ui";
import "./receipt.css";

const BASE = import.meta.env.VITE_API_URL || "";
const WIDTHS = [
  { key: "58", label: "58 mm" },
  { key: "80", label: "80 mm" },
  { key: "a4", label: "A4" },
  { key: "custom", label: "Custom" },
];
const PAGE = {
  "58": "size:58mm auto;margin:2mm",
  "80": "size:80mm auto;margin:3mm",
  a4: "size:A4;margin:12mm",
};
const STATUS = { paid: "Paid in full", partial: "Part payment", waived: "Fee waived", pending: "Pending" };

const money = (n, cur) =>
  `${cur || "KES"} ${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const day = (v) => (v ? new Date(v).toLocaleDateString() : "");
const read = (k, d) => {
  try { return localStorage.getItem(k) || d; } catch { return d; }
};

function Row({ k, v }) {
  if (v === undefined || v === null || v === "") return null;
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
      <span>{k}</span>
      <b style={{ textAlign: "right" }}>{v}</b>
    </div>
  );
}

export default function Statement({ studentId, onClose }) {
  const [state, setState] = useState({ loading: true });
  const [tries, setTries] = useState(0);
  const [width, setWidth] = useState(() => {
    const v = read("rcpt-width", "80");
    return ["58", "80", "a4", "custom"].includes(v) ? v : "80";
  });
  const [mmText, setMmText] = useState(() => read("rcpt-custom-mm", "72"));
  const mm = Math.min(120, Math.max(40, Number(mmText) || 72));
  const pageRule = width === "custom" ? `size:${mm}mm auto;margin:2mm` : PAGE[width];

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const r = await api(`/api/fees/students/${studentId}/statement/`);
        if (!live) return;
        if (!r.ok) { setState({ error: "Could not load the statement. Please try again." }); return; }
        setState({ data: await r.json() });
      } catch {
        if (live) setState({ error: "Could not load the statement. Please try again." });
      }
    })();
    return () => { live = false; };
  }, [studentId, tries]);

  const pickWidth = (key) => {
    setWidth(key);
    try { localStorage.setItem("rcpt-width", key); } catch { /* storage unavailable */ }
  };
  const changeMm = (e) => {
    const v = e.target.value.replace(/\D/g, "").slice(0, 3);
    setMmText(v);
    try { localStorage.setItem("rcpt-custom-mm", String(Math.min(120, Math.max(40, Number(v) || 72)))); } catch { /* storage unavailable */ }
  };

  const d = state.data;
  const cur = d && d.school.currency;
  const logo = d && d.school.logo ? (d.school.logo.startsWith("/") ? BASE + d.school.logo : d.school.logo) : "";
  const place = d ? [d.school.location, d.school.sub_county, d.school.county].filter(Boolean).join(", ") : "";
  const contact = d ? [d.school.phone, d.school.email].filter(Boolean).join(" | ") : "";

  return createPortal(
    <div className={`rcpt-portal rcpt-w${width}`} style={{ "--rcpt-mm": mm }} onClick={onClose}>
      <style>{`@media print{@page{${pageRule}}}`}</style>
      <div className="rcpt-dialog" role="dialog" aria-modal="true" aria-label="Fee statement" onClick={(e) => e.stopPropagation()}>
        <div className="rcpt-top rcpt-noprint">
          <h3>Fee statement</h3>
          <Button size="sm" kind="ghost" onClick={onClose} aria-label="Close statement">Close</Button>
        </div>
        {state.loading && <div className="rcpt-noprint"><Loading /></div>}
        {state.error && (
          <div className="rcpt-noprint">
            <Alert kind="err">{state.error}</Alert>
            <div className="rcpt-actions"><Button kind="secondary" onClick={() => { setState({ loading: true }); setTries((t) => t + 1); }}>Try again</Button></div>
          </div>
        )}
        {d && (
          <>
            <article className="rcpt-paper" aria-label="Fee statement">
              <header className="rcpt-head">
                {logo && <img className="rcpt-logo" src={logo} alt="" onError={(e) => { e.currentTarget.style.display = "none"; }} />}
                <b className="rcpt-school">{d.school.name}</b>
                {d.school.motto && <small>{d.school.motto}</small>}
                {place && <small>{place}</small>}
                {contact && <small>{contact}</small>}
              </header>
              <h4 className="rcpt-title">FEE STATEMENT</h4>
              <p className="rcpt-no">As of {day(d.as_of)}</p>
              <Row k="Student" v={d.student.name} />
              <Row k="Admission no" v={d.student.admission_number} />
              <Row k="Category" v={d.student.category === "boarder" ? "Boarder" : d.student.category === "day" ? "Day scholar" : ""} />
              <hr />
              {d.bills.length === 0 && <p>No fees billed yet.</p>}
              {d.bills.map((b, i) => (
                <div key={i} style={{ marginBottom: 8 }}>
                  <b>{b.fee}</b>
                  <div><small>{[b.term, b.year].filter(Boolean).join(" ")} | {STATUS[b.status] || b.status}</small></div>
                  <Row k="Due" v={money(b.amount_due, cur)} />
                  {Number(b.balance_brought_forward) !== 0 && <Row k="Brought forward" v={money(b.balance_brought_forward, cur)} />}
                  <Row k="Paid" v={money(b.paid, cur)} />
                  <Row k="Balance" v={money(b.balance, cur)} />
                </div>
              ))}
              <div className="rcpt-total"><span>TOTAL BILLED</span><b>{money(d.totals.billed, cur)}</b></div>
              <div className="rcpt-total"><span>TOTAL PAID</span><b>{money(d.totals.paid, cur)}</b></div>
              <div className="rcpt-total"><span>BALANCE DUE</span><b>{money(d.totals.balance, cur)}</b></div>
              {d.payments.length > 0 && (
                <>
                  <hr />
                  <b>Payments</b>
                  {d.payments.map((p, i) => (
                    <div key={i} style={{ marginTop: 4 }}>
                      <Row k={`${day(p.date)} ${p.receipt_number}`} v={money(p.amount, cur)} />
                      <div><small>{[p.fee, p.method].filter(Boolean).join(" | ")}</small></div>
                    </div>
                  ))}
                </>
              )}
              <footer className="rcpt-foot">
                <small>Quote the receipt number to verify a payment with the school.</small>
              </footer>
            </article>
            <div className="rcpt-widths rcpt-noprint" role="group" aria-label="Paper width">
              {WIDTHS.map((w) => (
                <button key={w.key} type="button" className={`rcpt-chip ${width === w.key ? "on" : ""}`} aria-pressed={width === w.key} onClick={() => pickWidth(w.key)}>{w.label}</button>
              ))}
              {width === "custom" && (
                <label className="rcpt-mm">Roll width (mm)
                  <input type="number" inputMode="numeric" min="40" max="120" value={mmText} onChange={changeMm} />
                </label>
              )}
            </div>
            <div className="rcpt-actions rcpt-noprint">
              <Button kind="teal" onClick={() => window.print()}>Print statement</Button>
            </div>
          </>
        )}
      </div>
    </div>,
    document.body
  );
}
