import { Button, Card, EmptyState } from "./ui";

const A = [
  ["Approve", "Approve Marks", "Approve"],
  ["Exams", "Exams", "Exams"],
  ["Reports", "Reports", "Reports"],
  ["Students", "Students", "Students"],
  ["Analytics", "Analytics", "Analytics"],
];
const row = { display: "flex", flexWrap: "wrap", gap: "8px" };

export default function Quick({ go, tabs }) {
  const items = A.filter(([t]) => tabs[t]);
  return (
    <Card title="Quick actions">
      {items.length === 0 ? (
        <EmptyState title="No shortcuts" text="Nothing is available for your role." />
      ) : (
        <div style={row}>
          {items.map(([t, label]) => (
            <Button key={t} kind="secondary" onClick={() => go(t)}>{label}</Button>
          ))}
        </div>
      )}
    </Card>
  );
}
