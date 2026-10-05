import { Button, Card, Badge, StatCard } from "./ui";

export default function TeacherTodo({ d, go }) {
  const m = d.my_marks_by_status || {};
  const draft = m.draft || 0;
  const wait = m.submitted || 0;
  const done = (m.approved || 0) + (m.locked || 0);
  const total = draft + wait + done;
  const ok = total > 0 && draft === 0;
  return (
    <div>
      <Card title="My marks this term">
        {total === 0 && <p>No marks entered yet this term.</p>}
        {draft > 0 && (
          <p>
            <Badge kind="warn">{draft} draft marks not submitted</Badge>{" "}
            <Button kind="secondary" onClick={() => go("Marks")}>Open marks</Button>
          </p>
        )}
        {ok && <Badge kind="ok">All entered marks are submitted</Badge>}
        {total === 0 && <Button onClick={() => go("Marks")}>Enter marks</Button>}
      </Card>
      <div className="mu-stats">
        <StatCard label="Draft" value={draft} />
        <StatCard label="Awaiting approval" value={wait} />
        <StatCard label="Approved or locked" value={done} />
      </div>
    </div>
  );
}
