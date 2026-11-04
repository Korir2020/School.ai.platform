import { useState, useEffect } from "react";
import { listAll as list } from "./api";
import { Card, DataTable, EmptyState, Loading } from "./ui";

const paths = ["subjects", "streams", "class-levels"];

export default function Mine({ d }) {
  const a = d.assignments || [];
  const [m, setM] = useState(null);
  useEffect(() => {
    const soft = (p) => list("/api/" + p + "/").catch(() => []);
    Promise.all(paths.map(soft)).then(([sj, sm, cl]) => setM({ sj, sm, cl }));
  }, []);
  if (!m) return <Loading />;
  const nm = (arr, id) => (arr.find((z) => z.id === id) || {}).name || id;
  const cols = [
    { label: "Subject", get: (x) => nm(m.sj, x.subject), sort: true },
    { label: "Class", get: (x) => nm(m.cl, x.class_level) + " " + nm(m.sm, x.stream),
      sort: true },
  ];
  return (
    <Card title="My classes">
      {a.length === 0 ? (
        <EmptyState title="No classes assigned yet"
          text="Ask the administrator to assign you to a class." />
      ) : (
        <DataTable cols={cols} rows={a} search="Search classes" />
      )}
    </Card>
  );
}
