import { useEffect, useState } from "react";
import { api, upload } from "./api";
import "./migration.css";

const CHECK_PATH = "/api/students/migration/check/";
const COMMIT_PATH = CHECK_PATH.replace("/check/", "/commit/");
const PHOTO_PATH = CHECK_PATH.replace("/check/", "/read-photo/");
const PAGE = 100;
const LINE = "1px solid rgba(128,128,128,.4)";
const TONE = {
  ready: ["#16a34a", "Ready"],
  needs_confirmation: ["#d97706", "Confirm"],
  blocked: ["#dc2626", "Blocked"],
};
const SEV = { block: "#dc2626", confirm: "#d97706", notice: "#6b7280" };
const btn = { minHeight: 44, padding: "0 16px", borderRadius: 10, border: LINE, background: "transparent", color: "inherit", font: "inherit", cursor: "pointer" };
const btnMain = { ...btn, background: "#2563eb", borderColor: "#2563eb", color: "#fff", fontWeight: 600 };
const card = { border: LINE, borderRadius: 12, padding: 12, marginBottom: 10 };
const inp = { display: "block", width: "100%", boxSizing: "border-box", minHeight: 44, marginTop: 4, padding: "0 10px", borderRadius: 10, border: LINE, background: "transparent", color: "inherit", font: "inherit", fontSize: 16 };
const FIX_LABELS = [
  ["first_name", "First name"],
  ["last_name", "Surname"],
  ["admission_number", "Admission number (leave blank for a temporary one)"],
  ["class_level", "Class, for example Grade 7 East"],
  ["stream", "Stream, if the class has streams"],
  ["assessment_number", "Assessment number (Grade 10 to 12 only)"],
];

function Chip({ n, label, color }) {
  return (
    <div style={{ ...card, flex: "1 1 90px", marginBottom: 0, textAlign: "center", borderColor: color || "rgba(128,128,128,.4)" }}>
      <div style={{ fontSize: 22, fontWeight: 700, color }}>{n}</div>
      <div style={{ fontSize: 12, opacity: 0.8 }}>{label}</div>
    </div>
  );
}

export default function MigrationCentre() {
  const [file, setFile] = useState(null);
  const [text, setText] = useState("");
  const [source, setSource] = useState("digital");
  const [res, setRes] = useState(null);
  const [conf, setConf] = useState({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [only, setOnly] = useState(true);
  const [limit, setLimit] = useState(PAGE);
  const [ask, setAsk] = useState(false);
  const [fixes, setFixes] = useState({});
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState({});
  const [pages, setPages] = useState([]);
  const [photoOn, setPhotoOn] = useState(null);
  const [reading, setReading] = useState(false);
  useEffect(() => {
    let alive = true;
    api(PHOTO_PATH).then((r) => r.json()).then((d) => { if (alive) setPhotoOn(!!d.enabled); }).catch(() => { if (alive) setPhotoOn(false); });
    return () => { alive = false; };
  }, []);
  const [done, setDone] = useState(null);
  const [nameOrder, setNameOrder] = useState("");

  async function run(c, f, t, o) {
    const fx = f || fixes;
    const order = o === undefined ? nameOrder : o;
    const body = t === undefined ? text : t;
    if (!file && !body.trim()) { setErr("Choose a file or paste the table first."); return; }
    setDone(null);
    setAsk(false);
    setBusy(true);
    setErr("");
    try {
      const fd = new FormData();
      if (file) fd.append("file", file); else fd.append("text", body);
      fd.append("source", source);
      if (c && Object.keys(c).length) fd.append("confirmations", JSON.stringify(c));
      if (Object.keys(fx).length) fd.append("fixes", JSON.stringify(fx));
      if (order) fd.append("name_order", order);
      const r = await upload(CHECK_PATH, fd, 60000);
      let data = null;
      try { data = await r.json(); } catch { data = null; }
      if (!r.ok) {
        setErr((data && data.detail) || "The check failed (" + r.status + "). Try again.");
        setRes(null);
      } else {
        setRes(data);
        setConf(c || {});
        setFixes(fx);
        setLimit(PAGE);
      }
    } catch (e) {
      setErr(e && e.name === "TimeoutError" ? "The server took too long to answer. It may be waking up. Wait a minute, then press Check again." : "Could not reach the server. Check your connection and try again.");
    }
    setBusy(false);
  }

  function accept(row, code) {
    const cur = { ...conf };
    const set = new Set(cur[row] || []);
    if (set.has(code)) set.delete(code); else set.add(code);
    if (set.size) cur[row] = [...set]; else delete cur[row];
    run(cur);
  }

  async function commit() {
    setBusy(true);
    setErr("");
    try {
      const fd = new FormData();
      if (file) fd.append("file", file); else fd.append("text", text);
      fd.append("source", source);
      if (Object.keys(conf).length) fd.append("confirmations", JSON.stringify(conf));
      if (Object.keys(fixes).length) fd.append("fixes", JSON.stringify(fixes));
      if (nameOrder) fd.append("name_order", nameOrder);
      const r = await upload(COMMIT_PATH, fd);
      let data = null;
      try { data = await r.json(); } catch { data = null; }
      if (!r.ok) {
        setErr((data && data.detail) || "Saving failed (" + r.status + "). Nothing was added.");
      } else {
        setDone(data);
        setRes(null); setFile(null); setText(""); setConf({}); setFixes({});
      }
    } catch {
      setErr("The connection dropped. Open the Students list to see whether the learners were added before you try again.");
    }
    setAsk(false);
    setBusy(false);
  }

  function fixBase(r) {
    return {
      first_name: r.first_name || "",
      last_name: r.last_name || "",
      admission_number: r.provisional_admission ? "" : (r.admission_number || ""),
      class_level: r.class_text || "",
      stream: r.stream_text || "",
      assessment_number: r.assessment_number || "",
    };
  }

  function openFix(r) {
    setDraft(fixBase(r));
    setEditing(r.row);
  }

  function saveFix(r) {
    const base = fixBase(r);
    const ch = { ...(fixes[r.row] || {}) };
    FIX_LABELS.forEach(([k]) => {
      const v = (draft[k] || "").trim();
      if (v !== (base[k] || "").trim()) ch[k] = v;
    });
    setEditing(null);
    if (JSON.stringify(ch) === JSON.stringify(fixes[r.row] || {})) return;
    run(conf, { ...fixes, [r.row]: ch });
  }

  function undoFix(r) {
    const nf = { ...fixes };
    delete nf[r.row];
    run(conf, nf);
  }

  function renderFix(r) {
    if (editing === r.row) {
      return (
        <div style={{ marginTop: 10 }}>
          {FIX_LABELS.map(([k, label]) => (
            <label key={k} style={{ display: "block", fontSize: 13, marginBottom: 8 }}>
              {label}
              <input value={draft[k] || ""} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} style={inp} />
            </label>
          ))}
          <div style={{ display: "flex", gap: 8 }}>
            <button style={{ ...btn, flex: 1 }} onClick={() => setEditing(null)}>Cancel</button>
            <button style={{ ...btnMain, flex: 1 }} disabled={busy} onClick={() => saveFix(r)}>Save and re-check</button>
          </div>
        </div>
      );
    }
    const mine = fixes[r.row];
    if (r.status === "ready" && !mine) return null;
    return (
      <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        {r.status !== "ready" && <button style={btn} disabled={busy} onClick={() => openFix(r)}>Fix</button>}
        {mine && <button style={btn} disabled={busy} onClick={() => undoFix(r)}>Undo my fix</button>}
        {mine && <span style={{ fontSize: 12, opacity: 0.8 }}>Corrected by you</span>}
      </div>
    );
  }

  async function shrink(f) {
    try {
      const url = URL.createObjectURL(f);
      const img = await new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = url; });
      const k = Math.min(1, 2400 / Math.max(img.width, img.height));
      const cv = document.createElement("canvas");
      cv.width = Math.round(img.width * k);
      cv.height = Math.round(img.height * k);
      cv.getContext("2d").drawImage(img, 0, 0, cv.width, cv.height);
      URL.revokeObjectURL(url);
      return await new Promise((ok) => cv.toBlob(ok, "image/jpeg", 0.88));
    } catch { return null; }
  }

  async function addPage(e) {
    const f = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!f) return;
    if (pages.length >= 20) { setErr("Add at most 20 pages at a time."); return; }
    setErr("");
    const blob = await shrink(f);
    if (!blob) { setErr("This photo could not be opened. Save it as a JPG and try again."); return; }
    setPages((p) => [...p, { name: f.name, blob, status: "waiting" }]);
    setRes(null);
  }

  function removePage(i) {
    setPages((p) => p.filter((_, k) => k !== i));
    setRes(null); setNameOrder(""); setConf({}); setFixes({});
  }

  async function readPages() {
    setReading(true); setErr(""); setRes(null); setNameOrder(""); setConf({}); setFixes({});
    const list = pages.map((p) => ({ ...p }));
    const upd = () => setPages(list.map((p) => ({ ...p })));
    let headers = list[0] && list[0].status === "done" ? list[0].headers : null;
    for (let i = 0; i < list.length; i++) {
      if (list[i].status === "done") continue;
      list[i].status = "reading"; list[i].msg = ""; upd();
      try {
        const fd = new FormData();
        fd.append("photo", list[i].blob, "page.jpg");
        fd.append("page", String(i + 1));
        if (headers) fd.append("headers", JSON.stringify(headers));
        const r = await upload(PHOTO_PATH, fd);
        let d = null;
        try { d = await r.json(); } catch { d = null; }
        if (!r.ok) {
          list[i].status = "failed";
          list[i].msg = (d && d.detail) || "Page " + (i + 1) + " could not be read (" + r.status + ").";
          upd(); setReading(false); return;
        }
        Object.assign(list[i], { status: "done", headers: d.headers, rows: d.rows, unreadable: d.unreadable, to_check: d.to_check, notes: d.notes || "", msg: "" });
        if (!headers) headers = d.headers;
        upd();
      } catch {
        list[i].status = "failed";
        list[i].msg = "Page " + (i + 1) + " could not be sent. Check your connection and retry.";
        upd(); setReading(false); return;
      }
    }
    setReading(false);
    const lines = [headers.join("\t")];
    list.forEach((p) => p.rows.forEach((row) => lines.push(row.join("\t"))));
    const t = lines.join("\n");
    setText(t); setFile(null);
    await run({}, {}, t);
  }

  const sum = res && res.summary ? res.summary : null;
  const rows = res && res.rows ? res.rows : [];
  const shown = (only ? rows.filter((r) => r.status !== "ready") : rows).slice(0, limit);
  const total = only ? rows.filter((r) => r.status !== "ready").length : rows.length;

  const canAdd = !!sum && sum.ready > 0 && !(res.file_issues || []).some((i) => i.severity === "block");
  const goAdd = () => {
    setAsk(true);
    setTimeout(() => { const el = document.getElementById("add-confirm"); if (el) el.scrollIntoView({ block: "center" }); }, 60);
  };
  const step = done ? 5 : ask ? 4 : sum && (sum.blocked > 0 || sum.needs_confirmation > 0 || (res.file_issues || []).length > 0) ? 3 : sum ? 2 : 1;

  return (
    <div className="mc-page">
      <h2 style={{ marginTop: 0 }}>Migration Centre</h2>
      <p style={{ opacity: 0.85, marginTop: 0 }}>
        Add many learners at once. Upload an Excel, CSV or typed PDF file, or paste the table. Nothing is added until you confirm at the end.
      </p>

      <div role="list" aria-label="Progress" className="mc-steps">
        {["Upload", "Check", "Fix", "Add", "Done"].map((name, i) => (
          <div key={name} role="listitem" aria-current={step === i + 1 ? "step" : undefined} className={"mc-step" + (step === i + 1 ? " is-current" : step > i + 1 ? " is-done" : "")}>
            <span className="mc-dot">{step > i + 1 ? "\u2713" : i + 1}</span>
            <span className="mc-label">{name}</span>
          </div>
        ))}
      </div>

      {step === 1 && <div style={{ ...card, fontSize: 14 }}><b>Next:</b> choose your file or paste the list, then press "2. Check the list".</div>}
      {(step === 2 || step === 3) && canAdd && (
        <button style={{ ...btnMain, width: "100%", marginBottom: 10 }} disabled={busy} onClick={goAdd}>
          Next: add {sum.ready} ready learner(s)
        </button>
      )}
      {step === 3 && !canAdd && <div style={{ ...card, fontSize: 14 }}><b>Next:</b> fix the file or the marked learners, then press "2. Check the list" again.</div>}
      <div style={card}>
        <label style={{ display: "block", fontWeight: 600, marginBottom: 6 }}>1. Choose a file (.xlsx, .csv or typed .pdf)</label>
        <input
          type="file"
          accept=".csv,.xlsx,.pdf,.tsv,.txt"
          onChange={(e) => { setFile(e.target.files && e.target.files[0] ? e.target.files[0] : null); setRes(null); setNameOrder(""); setConf({}); setFixes({}); }}
          style={{ width: "100%", minHeight: 44 }}
        />
        <label style={{ display: "block", fontWeight: 600, margin: "12px 0 6px" }}>or paste the table here</label>
        <textarea
          value={text}
          onChange={(e) => { setText(e.target.value); setRes(null); setNameOrder(""); setConf({}); setFixes({}); }}
          placeholder={"Admission No, First name, Surname, Class\n1001, Amina, Otieno, Grade 7 East"}
          rows={5}
          disabled={!!file}
          style={{ width: "100%", boxSizing: "border-box", borderRadius: 10, border: LINE, padding: 10, font: "inherit", background: "transparent", color: "inherit" }}
        />
        {file && (
          <div style={{ marginTop: 6, fontSize: 13 }}>
            Using file: <b>{file.name}</b>{" "}
            <button style={{ ...btn, minHeight: 36, padding: "0 10px" }} onClick={() => { setFile(null); setRes(null); setNameOrder(""); setConf({}); setFixes({}); }}>Remove</button>
          </div>
        )}
        <label style={{ display: "block", fontWeight: 600, margin: "12px 0 6px" }}>Where did this list come from?</label>
        <select value={source} onChange={(e) => { setSource(e.target.value); setRes(null); setNameOrder(""); setConf({}); setFixes({}); }} style={{ ...btn, width: "100%" }}>
          <option value="digital">A computer file (Excel, CSV)</option>
          <option value="paper">A handwritten or typed register</option>
        </select>
        {source === "paper" && (
          <div style={{ ...card, marginTop: 12, marginBottom: 0 }}>
            <b>Photos of the register</b>
            {photoOn === false ? (
              <div style={{ fontSize: 14, marginTop: 6 }}>Photo reading is not switched on yet. For now, use an Excel, CSV or typed PDF file, or type the learners into the box above.</div>
            ) : (
              <>
                <div style={{ fontSize: 14, margin: "6px 0 10px" }}>
                  Add one photo per page, in order. Keep the whole table in the frame, flat, in good light. Anything that cannot be read is marked for you to type. Nothing is skipped quietly.
                </div>
                {pages.map((p, i) => (
                  <div key={i} style={{ borderTop: LINE, padding: "8px 0", fontSize: 14 }}>
                    <b>Page {i + 1}</b>{" · "}
                    {p.status === "waiting" ? "waiting" : p.status === "reading" ? "reading..." : p.status === "done" ? p.rows.length + " lines read, " + p.unreadable + " unreadable, " + p.to_check + " to check" : "failed"}
                    {p.notes ? <div style={{ opacity: 0.8 }}>Reader's note: {p.notes}</div> : null}
                    {p.status === "failed" && <div role="alert" style={{ color: "#dc2626", marginTop: 4 }}>{p.msg}</div>}
                    {!reading && <div><button style={{ ...btn, minHeight: 36, padding: "0 10px", marginTop: 6 }} onClick={() => removePage(i)}>Remove</button></div>}
                  </div>
                ))}
                <label style={{ ...btn, display: "flex", alignItems: "center", justifyContent: "center", marginTop: 8 }}>
                  + Add a page photo
                  <input type="file" accept="image/*" onChange={addPage} style={{ display: "none" }} />
                </label>
                <button style={{ ...btnMain, width: "100%", marginTop: 10 }} disabled={busy || reading || pages.length === 0} onClick={readPages}>
                  {reading ? "Reading..." : pages.some((p) => p.status === "failed") ? "Retry from the failed page" : "Read " + pages.length + " page(s)"}
                </button>
              </>
            )}
          </div>
        )}
        <button style={{ ...btnMain, width: "100%", marginTop: 14 }} disabled={busy} onClick={() => run({})}>
          {busy ? "Checking..." : "2. Check the list"}
        </button>
      </div>

      {done && (
        <div role="status" style={{ ...card, borderColor: "#16a34a", background: "rgba(22,163,74,.1)" }}>
          <b>Done.</b> {done.created} learner(s) added{done.skipped ? ", " + done.skipped + " left out" : ""}. Find them under Students. To add the left-out ones, fix your file and check it again.
        <a href="#Students" style={{ ...btnMain, display: "block", textAlign: "center", textDecoration: "none", marginTop: 8, boxSizing: "border-box" }}>Open the Students list</a>
      
        </div>
      )}

      {err && (
        <div role="alert" style={{ ...card, borderColor: "#dc2626", background: "rgba(220,38,38,.1)" }}>{err}</div>
      )}

      {res && (
        <>
          {(res.needs_input || []).filter((n) => n.code === "name_order").map((n) => (
          <div key="name_order" style={{ border: "2px solid #b45309", borderRadius: 8, padding: 12, margin: "10px 0" }}>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>Which name comes first?</div>
            <div style={{ marginBottom: 8 }}>{n.message}</div>
            {(n.sample || []).length > 0 && (
              <div style={{ marginBottom: 8 }}>For example: {n.sample.slice(0, 3).join(" | ")}</div>
            )}
            <button style={{ ...btn, minHeight: 44, marginRight: 8 }} disabled={busy}
              onClick={() => { setNameOrder("first_last"); run(conf, fixes, undefined, "first_last"); }}>
              First name first
            </button>
            <button style={{ ...btn, minHeight: 44 }} disabled={busy}
              onClick={() => { setNameOrder("last_first"); run(conf, fixes, undefined, "last_first"); }}>
              Surname first
            </button>
          </div>
        ))}
        {(res.file_issues || []).map((i, k) => (
            <div key={k} role="alert" style={{ ...card, borderColor: SEV[i.severity] || "#6b7280", background: i.severity === "block" ? "rgba(220,38,38,.1)" : "rgba(128,128,128,.08)" }}>
              <b style={{ color: SEV[i.severity] || "inherit" }}>{i.severity === "block" ? "Fix the file: " : "Note: "}</b>
              {i.message}
            </div>
          ))}

          {sum && (
            <>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
                <Chip n={sum.total} label="Learners" />
                <Chip n={sum.ready} label="Ready" color="#16a34a" />
                <Chip n={sum.needs_confirmation} label="To confirm" color="#d97706" />
                <Chip n={sum.blocked} label="Blocked" color="#dc2626" />
              </div>
              {Object.keys(fixes).length > 0 && (
                <div style={{ ...card, fontSize: 14 }}>
                  You corrected {Object.keys(fixes).length} row(s) here. The file itself is unchanged.{" "}
                  <button style={{ ...btn, minHeight: 36, padding: "0 10px" }} disabled={busy} onClick={() => run(conf, {})}>Undo all</button>
                </div>
              )}
              {sum.temporary_admission > 0 && (
                <div style={{ ...card, fontSize: 14 }}>
                  {sum.temporary_admission} learner(s) have no admission number and will get a temporary one.
                </div>
              )}
              {sum.by_class && Object.keys(sum.by_class).length > 0 && (
                <div style={{ ...card, fontSize: 14 }}>
                  <b>By class:</b>{" "}
                  {Object.entries(sum.by_class).map(([k, v]) => k + " (" + v + ")").join(", ")}
                </div>
              )}
              <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
                <button style={{ ...btn, flex: 1, fontWeight: only ? 700 : 400 }} onClick={() => { setOnly(true); setLimit(PAGE); }}>Problems only</button>
                <button style={{ ...btn, flex: 1, fontWeight: only ? 400 : 700 }} onClick={() => { setOnly(false); setLimit(PAGE); }}>All learners</button>
              </div>
              {sum.blocked > 0 && (
                <div style={{ ...card, borderColor: "#dc2626", fontSize: 14 }}>
                  Blocked learners can't be added until you fix them in your file. Correct the file, choose it again, and check again.
                </div>
              )}
            </>
          )}

          {sum && sum.ready > 0 && !(res.file_issues || []).some((i) => i.severity === "block") && (
            ask ? (
              <div id="add-confirm" style={{ ...card, borderColor: "#2563eb" }}>
                <b>Add {sum.ready} learner(s) now?</b>
                <div style={{ fontSize: 14, margin: "6px 0 10px" }}>
                  {sum.needs_confirmation + sum.blocked > 0 ? (sum.needs_confirmation + sum.blocked) + " will be left out (blocked, or not yet accepted). " : ""}
                  Added learners go into the classes shown above. This cannot be undone from this screen.
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button style={{ ...btn, flex: 1 }} disabled={busy} onClick={() => setAsk(false)}>Cancel</button>
                  <button style={{ ...btnMain, flex: 1 }} disabled={busy} onClick={commit}>{busy ? "Adding..." : "Yes, add them"}</button>
                </div>
              </div>
            ) : (
              <button style={{ ...btnMain, width: "100%", marginBottom: 10 }} disabled={busy} onClick={() => setAsk(true)}>
                3. Add {sum.ready} ready learner(s)
              </button>
            )
          )}

          {total === 0 && rows.length > 0 && only && (
            <div style={{ ...card, borderColor: "#16a34a" }}>No problems found. Every learner is ready.</div>
          )}

          {shown.map((r) => {
            const t = TONE[r.status] || ["#6b7280", r.status];
            const given = conf[r.row] || [];
            return (
              <div key={r.row} style={{ ...card, borderLeft: "5px solid " + t[0] }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
                  <b>{(r.first_name || "") + " " + (r.last_name || "")}</b>
                  <span style={{ color: t[0], fontWeight: 700, fontSize: 13 }}>{t[1]}</span>
                </div>
                <div style={{ fontSize: 13, opacity: 0.85 }}>
                  Row {r.row} · Adm {r.admission_number || "none"}{r.provisional_admission ? " (temporary)" : ""} · {r.class_label || "No class"}
                </div>
                {renderFix(r)}
                {(r.issues || []).map((i, k) => {
                  const isConfirm = i.severity === "confirm";
                  const done = given.includes(i.code);
                  return (
                    <div key={k} style={{ marginTop: 8, fontSize: 14 }}>
                      <span style={{ color: SEV[i.severity] || "inherit", fontWeight: 600 }}>
                        {i.severity === "block" ? "Problem: " : isConfirm ? "Check: " : "Note: "}
                      </span>
                      {i.message}
                      {isConfirm && (
                        <div>
                          <button style={{ ...btn, marginTop: 6, background: done ? "rgba(22,163,74,.15)" : "transparent" }} disabled={busy} onClick={() => accept(r.row, i.code)}>
                            {done ? "Accepted. Tap to undo" : "This is correct, accept"}
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })}

          {total > shown.length && (
            <button style={{ ...btn, width: "100%" }} onClick={() => setLimit(limit + PAGE)}>
              Show more ({total - shown.length} left)
            </button>
          )}
        </>
      )}
    </div>
  );
}
