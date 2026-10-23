import { useState, useEffect } from "react";
import { api, listAll as list } from "./api";
import { useToast } from "./toastctx";
import { Button, Select, Card, Badge } from "./ui";
import { ConfirmDialog, EmptyState, Loading, ErrorState } from "./ui";

const P = "/api/levels/";
const kindNames = { opener: "Opener", mid: "Mid-term", end: "End-term" };
const kinds = { draft: "info", submitted: "warn", approved: "ok", locked: "teal" };

async function errText(r) {
  try { const j = await r.json(); return j.message || j.detail || "Request failed."; }
  catch { return "Request failed (" + r.status + ")."; }
}

export default function LevelEntry({ d }) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [bad, setBad] = useState(false);
  const [bt, setBt] = useState(0);
  const [sel, setSel] = useState("");
  const [kind, setKind] = useState("end");
  const [ros, setRos] = useState(null);
  const [edits, setEdits] = useState({});
  const [busy, setBusy] = useState(false);
  const [ask, setAsk] = useState(false);
  const [tries, setTries] = useState(0);

  useEffect(() => {
    let live = true;
    const get = (p) => list("/api/" + p + "/");
    const soft = (p) => get(p).catch(() => []);
    Promise.all([get("terms"), get("teacher-assignments"), soft("subjects"), soft("streams"), soft("class-levels")])
      .then(([tm, ta, sj, sm, cl]) => { if (live) { setData({ tm, ta, sj, sm, cl }); setBad(false); } })
      .catch(() => { if (live) setBad(true); });
    return () => { live = false; };
  }, [bt]);

  const term = data && d.active_term ? data.tm.find((t) => t.id === d.active_term.id) : null;
  const a = data
    ? (data.ta.find((x) => String(x.id) === sel) || (d.assignments || []).find((x) => String(x.id) === sel))
    : null;
  const url = a && term
    ? P + "roster/?" + new URLSearchParams({
        subject_id: a.subject, stream_id: a.stream, year_id: term.academic_year, term_id: term.id, type: kind,
      }).toString()
    : "";

  useEffect(() => {
    if (!url) return undefined;
    let live = true;
    api(url)
      .then(async (r) => {
        if (!live) return;
        if (!r.ok) { const m = await errText(r); if (live) setRos({ url, error: m }); return; }
        const j = await r.json();
        if (live) setRos({ url, levels: j.levels || [], rows: j.rows || [] });
      })
      .catch(() => { if (live) setRos({ url, error: "Could not load learners." }); });
    return () => { live = false; };
  }, [url, tries]);

  if (bad) return <ErrorState text="Could not load your classes." onRetry={() => { setBad(false); setBt(bt + 1); }} />;
  if (!data) return <Loading />;
  if (!d.active_term) return <EmptyState title="No active term" text="Ask the school admin to set the active term." />;
  if (!term) return <ErrorState text="Active term not found." onRetry={() => setBt(bt + 1)} />;

  const pick = (arr, id) => arr.find((z) => z.id === id) || {};
  const label = (x) => (pick(data.sj, x.subject).name || "Subject " + x.subject)
    + " - " + (pick(data.cl, x.class_level).name || x.class_level)
    + " " + (pick(data.sm, x.stream).name || x.stream);

  const cur = ros && ros.url === url ? ros : null;
  const rows = cur && cur.rows ? cur.rows : [];
  const levels = cur && cur.levels ? cur.levels : [];
  const lab = (k) => (levels.find((l) => l.key === k) || {}).label || k;
  const editable = (r) => !r.status || r.status === "draft";
  const mine = (r) => edits[r.student_id] || {};
  const levelOf = (r) => mine(r).level ?? r.level;
  const commentOf = (r) => mine(r).comment ?? r.comment ?? "";
  const setE = (r, patch) => setEdits({ ...edits, [r.student_id]: { ...mine(r), ...patch } });
  const dirty = rows.filter((r) => editable(r) && edits[r.student_id] && levelOf(r)
    && (levelOf(r) !== r.level || commentOf(r) !== (r.comment || "")));
  const drafts = rows.filter((r) => r.status === "draft" && r.id);

  const save = async () => {
    setBusy(true);
    let ok = 0, fail = 0, first = "";
    const left = { ...edits };
    for (const r of dirty) {
      try {
        const res = await api(P + "save/", "POST", {
          student_id: r.student_id, subject_id: a.subject, year_id: term.academic_year,
          term_id: term.id, type: kind, level: levelOf(r), comment: commentOf(r),
        });
        if (res.ok) { ok++; delete left[r.student_id]; }
        else { fail++; if (!first) first = await errText(res); }
      } catch { fail++; }
    }
    setBusy(false);
    toast("Saved " + ok + ", failed " + fail + (first ? ": " + first : ""), fail ? "err" : "ok");
    setEdits(left);
    setTries(tries + 1);
  };

  const submit = async () => {
    setAsk(false);
    setBusy(true);
    let ok = 0, fail = 0;
    for (const r of drafts) {
      try {
        const res = await api(P + "move/", "POST", { result_id: r.id, action: "submit" });
        if (res.ok) ok++; else fail++;
      } catch { fail++; }
    }
    setBusy(false);
    toast("Submitted " + ok + ", failed " + fail, fail ? "err" : "ok");
    setTries(tries + 1);
  };

  const wrap = { display: "flex", flexWrap: "wrap", gap: 6 };
  const box = { width: "100%", padding: 8, boxSizing: "border-box" };

  return (
    <div>
      <h2>Enter levels</h2>
      <p>{kindNames[kind]}. Level wording is set by your school, not official.</p>
      <Card>
        <Select id="lv-sel" label="Class and subject" value={sel}
          onChange={(e) => { setSel(e.target.value); setEdits({}); }}>
          <option value="">Choose class and subject</option>
          {(d.assignments || data.ta).map((x) => <option key={x.id} value={x.id}>{label(x)}</option>)}
        </Select>
        {a && <Select id="lv-kind" label="Assessment" value={kind}
          onChange={(e) => { setKind(e.target.value); setEdits({}); }}>
          {Object.keys(kindNames).map((k) => <option key={k} value={k}>{kindNames[k]}</option>)}
        </Select>}
      </Card>
      {a && cur === null && <Loading />}
      {a && cur && cur.error && <ErrorState text={cur.error} onRetry={() => setTries(tries + 1)} />}
      {a && cur && !cur.error && levels.length === 0 && (
        <EmptyState title="No level wording set" text="Ask the school admin to set up level wording for this class level." />
      )}
      {a && cur && !cur.error && levels.length > 0 && (
        <div>
          {rows.length === 0 && <EmptyState title="No learners" text="No learners are enrolled in this class." />}
          {rows.map((r) => (
            <Card key={r.student_id} title={r.name}>
              <p>{r.status ? <Badge kind={kinds[r.status] || "info"}>{r.status}</Badge> : <Badge>not entered</Badge>}</p>
              {editable(r) ? (
                <div>
                  <div style={wrap}>
                    {levels.map((l) => (
                      <Button key={l.key} size="sm" kind={levelOf(r) === l.key ? "teal" : "ghost"}
                        onClick={() => setE(r, { level: l.key })}>{l.label}</Button>
                    ))}
                  </div>
                  <p><input type="text" style={box} value={commentOf(r)} aria-label={"Comment for " + r.name}
                    placeholder="Comment (optional)" onChange={(e) => setE(r, { comment: e.target.value })} /></p>
                </div>
              ) : (
                <div>
                  <p>Level: {lab(r.level)}</p>
                  {r.comment && <p>{r.comment}</p>}
                  <p>Already {r.status}. It can no longer be changed here.</p>
                </div>
              )}
            </Card>
          ))}
          {rows.length > 0 && (
            <Card>
              {dirty.length > 0 && drafts.length > 0 && <p>Save your changes before submitting.</p>}
              <p><Button kind="teal" busy={busy} disabled={dirty.length === 0} onClick={save}>
                Save levels{dirty.length ? " (" + dirty.length + ")" : ""}</Button></p>
              <p><Button busy={busy} disabled={drafts.length === 0 || dirty.length > 0} onClick={() => setAsk(true)}>
                Submit {drafts.length} for approval</Button></p>
            </Card>
          )}
        </div>
      )}
      {ask && <ConfirmDialog title="Submit these levels?" confirm="Submit"
        text="Submitted levels go to the admin for approval." onYes={submit} onNo={() => setAsk(false)} />}
    </div>
  );
}
