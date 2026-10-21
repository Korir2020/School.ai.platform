import { useEffect, useState } from "react";
import { api } from "./api";
import { Button, Card, Select, Badge, Alert, EmptyState, Loading } from "./ui";

const P = "/api/report-module/";
const FIELDS = [
  ["class_teacher", "Class teacher remark"],
  ["principal", "Principal remark (admin only)"],
];

async function errText(r) {
  try { const d = await r.json(); return d.message || d.detail || "Request failed."; }
  catch { return "Request failed (" + r.status + ")."; }
}

export default function ReportComments({ exam, cls, students }) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState(null);
  const [msg, setMsg] = useState("");
  const [sid, setSid] = useState("");
  const [field, setField] = useState("class_teacher");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState("");
  const [editId, setEditId] = useState("");
  const [editText, setEditText] = useState("");

  const names = {};
  students.forEach((s) => { names[s.id] = s.name + " (Adm " + s.adm_no + ")"; });
  const label = {};
  FIELDS.forEach((f) => { label[f[0]] = f[1].split(" (")[0]; });

  const [n, setN] = useState(0);

  useEffect(() => {
    if (!open) return undefined;
    let live = true;
    api(P + "comments/?" + new URLSearchParams({ exam_id: exam, class_name: cls }))
      .then(async (r) => {
        if (!live) return;
        if (!r.ok) { setMsg(await errText(r)); setRows([]); return; }
        const d = await r.json();
        if (live) setRows(d.comments || []);
      })
      .catch(() => { if (live) { setMsg("Could not load comments."); setRows([]); } });
    return () => { live = false; };
  }, [open, exam, cls, n]);

  const act = async (key, path, method, body) => {
    setMsg(""); setBusy(key);
    let ok = false;
    try {
      const r = await api(P + path, method, body);
      if (!r.ok) { setMsg(await errText(r)); }
      else { ok = true; setN((x) => x + 1); }
    } catch { setMsg("Request failed."); }
    setBusy("");
    return ok;
  };

  const saveDraft = async () => {
    if (!sid || !text.trim()) { setMsg("Choose a student and write the comment first."); return; }
    if (await act("new", "comments/draft/", "POST", { exam_id: exam, student_id: sid, field, text: text.trim() })) setText("");
  };
  const aiDraft = async () => {
    if (!sid) { setMsg("Choose a student first."); return; }
    await act("ai", "comments/draft/", "POST", { exam_id: exam, student_id: sid, field });
  };
  const saveEdit = async (id) => {
    if (!editText.trim()) { setMsg("The comment cannot be empty."); return; }
    if (await act("e" + id, "comments/" + id + "/", "PUT", { text: editText.trim() })) setEditId("");
  };

  const box = { width: "100%", minHeight: 80, padding: 8, boxSizing: "border-box" };

  return (
    <Card title="Comments">
      <p><Button onClick={() => setOpen(!open)}>{open ? "Hide comments" : "Review comments"}</Button></p>
      {open && (
        <div>
          {msg && <Alert>{msg}</Alert>}
          <Select id="rc-student" label="Student" value={sid} onChange={(e) => setSid(e.target.value)}>
            <option value="">Choose student</option>
            {students.map((s) => <option key={s.id} value={s.id}>{names[s.id]}</option>)}
          </Select>
          <Select id="rc-field" label="Comment for" value={field} onChange={(e) => setField(e.target.value)}>
            {FIELDS.map((f) => <option key={f[0]} value={f[0]}>{f[1]}</option>)}
          </Select>
          <p><textarea style={box} value={text} onChange={(e) => setText(e.target.value)} placeholder="Write the comment, or use AI draft" /></p>
          <p>
            <Button busy={busy === "new"} onClick={saveDraft}>Save as draft</Button>{" "}
            <Button busy={busy === "ai"} onClick={aiDraft}>AI draft</Button>
          </p>
          {rows === null && <Loading />}
          {rows && rows.length === 0 && <EmptyState title="No comments yet" text="Drafts you save appear here for approval." />}
          {rows && rows.map((c) => (
            <Card key={c.id} title={(names[c.student_id] || c.student_id) + " - " + (label[c.field] || c.field)}>
              <p><Badge kind={c.status === "approved" ? undefined : "warn"}>{c.status}</Badge> Source: {c.source}{c.edited ? " (edited)" : ""}</p>
              {editId === c.id ? (
                <div>
                  <p><textarea style={box} value={editText} onChange={(e) => setEditText(e.target.value)} /></p>
                  {c.status === "approved" && <p>Editing an approved comment sends it back for approval.</p>}
                  <p>
                    <Button busy={busy === "e" + c.id} onClick={() => saveEdit(c.id)}>Save</Button>{" "}
                    <Button onClick={() => setEditId("")}>Cancel</Button>
                  </p>
                </div>
              ) : (
                <div>
                  <p>{c.text}</p>
                  <p>
                    <Button onClick={() => { setEditId(c.id); setEditText(c.text); }}>Edit</Button>{" "}
                    {c.status === "draft" && (
                      <span>
                        <Button busy={busy === "a" + c.id} onClick={() => act("a" + c.id, "comments/" + c.id + "/approve/", "POST")}>Approve</Button>{" "}
                        <Button busy={busy === "r" + c.id} onClick={() => act("r" + c.id, "comments/" + c.id + "/reject/", "POST")}>Reject</Button>
                      </span>
                    )}
                  </p>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </Card>
  );
}
