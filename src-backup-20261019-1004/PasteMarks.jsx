import { useState } from "react";
import { Button, Alert } from "./ui";

const key = (s) => String(s || "").toLowerCase().replace(/\s+/g, " ").trim();

export default function PasteMarks({ rows, st, vals, setVals }) {
  const [text, setText] = useState(""), [res, setRes] = useState(null);
  const fill = () => {
    const map = {};
    rows.filter((r) => !r.o).forEach((r) => {
      const s = st.find((x) => x.id === r.student);
      if (!s) return;
      map[key(s.first_name + " " + s.last_name)] = r.student;
      map[key(s.last_name + " " + s.first_name)] = r.student;
      if (s.admission_number) map[key(s.admission_number)] = r.student;
    });
    const next = { ...vals }, miss = [];
    let ok = 0;
    text.split("\n").forEach((ln) => {
      const t = ln.trim();
      if (!t) return;
      const m = t.match(/^(.*?)[\s,;]+(\d+(?:\.\d+)?)$/);
      const sid = m ? map[key(m[1])] : undefined;
      if (sid) { next[sid] = m[2]; ok++; } else miss.push(t);
    });
    setVals(next); setText(""); setRes({ ok, miss });
  };
  return (
    <details>
      <summary>Paste marks from a spreadsheet</summary>
      <p>One student per line: name or admission number, then the mark.</p>
      <textarea rows={5} style={{ width: "100%" }} value={text}
        aria-label="Marks pasted from a spreadsheet"
        onChange={(e) => setText(e.target.value)} />
      <Button kind="secondary" size="sm" onClick={fill}
        disabled={!text.trim()}>Fill marks</Button>
      {res && <Alert kind={res.miss.length ? "err" : "info"}>
        {res.ok} filled. Check them, then press Save marks.
        {res.miss.length > 0 && " Not matched: " + res.miss.slice(0, 5).join("; ")}
      </Alert>}
    </details>
  );
}
