import { useState, useEffect } from "react";
import { api, listAll } from "./api";
import { Button, Card, Select, Badge, Alert } from "./ui";
import { EmptyState, Loading, ErrorState } from "./ui";

export default function ReportCards({ d }) {
  const [st, setSt] = useState(null);
  const [rc, setRc] = useState(null);
  const [busy, setBusy] = useState(false);
  const [bad, setBad] = useState("");
  const [tries, setTries] = useState(0);
  const termId = d.active_term && d.active_term.id;
  useEffect(() => {
    listAll("/api/students/").then(setSt).catch(() => setBad("students"));
  }, [tries]);
  const open = async (id) => {
    setBad("");
    if (!id) return setRc(null);
    setBusy(true);
    try {
      const r = await api("/api/report-card/" + id + "/" + termId + "/");
      if (!r.ok) throw new Error("card");
      setRc(await r.json());
    } catch {
      setRc(null);
      setBad("card");
    }
    setBusy(false);
  };
  if (!termId) {
    return <EmptyState title="No active term" text="Set an active term first." />;
  }
  if (bad === "students") {
    const retry = () => { setBad(""); setTries(tries + 1); };
    return <ErrorState text="Could not load students." onRetry={retry} />;
  }
  if (!st) return <Loading />;
  const subs = rc ? rc.subjects : [];
  const res = (rc && rc.published_results) || [];
  return (
    <div>
      <Card title="Report cards">
        <Select id="rc-student" label="Student"
          onChange={(e) => open(e.target.value)}>
          <option value="">Choose student</option>
          {st.map((s) => (
            <option key={s.id} value={s.id}>{s.first_name} {s.last_name}</option>
          ))}
        </Select>
      </Card>
      {busy && <Loading />}
      {bad === "card" && <Alert>Could not load this report card.</Alert>}
      {rc && !busy && (
        <Card title={rc.student.name + " (Adm " + rc.student.admission_number + ")"}>
          <p>{rc.term}, {rc.academic_year}</p>
          {subs.length === 0 ? (
            <EmptyState title="No approved marks" text="Nothing approved yet." />
          ) : (
            <div className="mu-tablewrap"><table className="mu-table">
              <thead><tr><th>Subject</th><th>Average</th></tr></thead>
              <tbody>{subs.map((s) => (
                <tr key={s.subject}><td>{s.subject}</td><td>{s.average}%</td></tr>
              ))}</tbody>
            </table></div>
          )}
          <p><b>Overall: {rc.overall_average}%</b></p>
          {res.length > 0 && (
            <div className="mu-tablewrap"><table className="mu-table">
              <thead><tr><th>Exam</th><th>Class rank</th>
                <th>Stream rank</th></tr></thead>
              <tbody>{res.map((r) => (
                <tr key={r.exam}><td>{r.exam}</td><td>{r.class_rank}</td>
                  <td>{r.stream_rank}</td></tr>
              ))}</tbody>
            </table></div>
          )}
          {rc.pending_marks > 0 && (
            <Badge kind="warn">{rc.pending_marks} marks pending approval</Badge>
          )}
          <p><Button onClick={() => window.print()}>Print</Button></p>
        </Card>
      )}
    </div>
  );
}
