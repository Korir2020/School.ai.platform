import { useEffect, useState } from "react";
import { api } from "./api";
import { Alert, Button, ConfirmDialog, EmptyState, ErrorState, Field, Loading, Select, StatCard } from "./ui";
import "./feedback.css";

const MAX = 1000;
const STAR = "\u2605";
const KIND_TEXT = { rating: "Rating", idea: "Idea", problem: "Problem", review: "Review" };
const WRITE_KINDS = ["idea", "problem", "review"];

async function call(path, method = "GET", body) {
  const r = await api(path, method, body);
  let data = null;
  if (r.status !== 204) {
    try {
      data = await r.json();
    } catch {
      data = null;
    }
  }
  if (!r.ok) throw new Error((data && data.message) || "Something went wrong. Please try again.");
  return data;
}

function when(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString();
}

function Stars({ value }) {
  if (!value) return null;
  return (
    <span className="fb-rated" aria-label={value + " out of 5"}>
      {STAR.repeat(value)}
    </span>
  );
}

function Member() {
  const [mine, setMine] = useState(null);
  const [err, setErr] = useState("");
  const [note, setNote] = useState(null);
  const [tick, setTick] = useState(0);
  const [pick, setPick] = useState(0);
  const [rText, setRText] = useState(null);
  const [kind, setKind] = useState("idea");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState("");
  const [del, setDel] = useState(null);

  useEffect(() => {
    let live = true;
    call("/api/feedback/")
      .then((d) => {
        if (live) {
          setMine(d.results);
          setErr("");
        }
      })
      .catch((e) => {
        if (live) setErr(e.message);
      });
    return () => {
      live = false;
    };
  }, [tick]);

  const refresh = () => setTick((t) => t + 1);
  const mineRating = mine ? mine.find((e) => e.kind === "rating") : null;
  const stars = pick || (mineRating ? mineRating.rating : 0);
  const ratingText = rText === null ? (mineRating ? mineRating.text : "") : rText;

  const run = async (name, fn, okText) => {
    setBusy(name);
    setNote(null);
    try {
      await fn();
      setNote({ kind: "info", text: okText });
      refresh();
    } catch (e) {
      setNote({ kind: "err", text: e.message });
    }
    setBusy("");
  };

  const saveRating = () => {
    if (!stars) {
      setNote({ kind: "err", text: "Tap a star first." });
      return;
    }
    run(
      "rate",
      () => call("/api/feedback/", "POST", { kind: "rating", rating: stars, text: ratingText.trim() }),
      "Thank you. Your rating is saved."
    );
  };

  const send = () => {
    if (!text.trim()) {
      setNote({ kind: "err", text: "Please write something first." });
      return;
    }
    run(
      "send",
      async () => {
        await call("/api/feedback/", "POST", { kind, text: text.trim() });
        setText("");
      },
      "Thank you. Your feedback was sent."
    );
  };

  const remove = (id) => {
    setDel(null);
    run("del", () => call("/api/feedback/" + id + "/", "DELETE"), "Deleted.");
  };

  if (!mine && !err) return <Loading />;
  if (!mine) return <ErrorState text={err} onRetry={refresh} />;

  return (
    <div className="fb-wrap">
      <p className="plain">Tell the Marian team what you think. Only the Marian owner reads your feedback.</p>
      {note && <Alert kind={note.kind}>{note.text}</Alert>}

      <section className="fb-card">
        <h2>Rate Marian</h2>
        <div className="fb-stars" role="group" aria-label="Rating out of 5">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              type="button"
              className={n <= stars ? "on" : ""}
              aria-pressed={n === stars}
              aria-label={n + (n === 1 ? " star" : " stars")}
              onClick={() => setPick(n)}
            >
              {STAR}
            </button>
          ))}
        </div>
        <Field label="Comment (optional)" id="fb-rate-text">
          <textarea
            id="fb-rate-text"
            className="mu-input"
            rows={2}
            maxLength={MAX}
            value={ratingText}
            onChange={(e) => setRText(e.target.value)}
          />
        </Field>
        <Button busy={busy === "rate"} onClick={saveRating}>
          {mineRating ? "Update rating" : "Save rating"}
        </Button>
      </section>

      <section className="fb-card">
        <h2>Send feedback</h2>
        <Select label="Type" value={kind} onChange={(e) => setKind(e.target.value)}>
          {WRITE_KINDS.map((k) => (
            <option key={k} value={k}>
              {KIND_TEXT[k]}
            </option>
          ))}
        </Select>
        <Field label="Your message" id="fb-text" help={text.length + " / " + MAX}>
          <textarea
            id="fb-text"
            className="mu-input"
            rows={5}
            maxLength={MAX}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </Field>
        <Button busy={busy === "send"} onClick={send}>
          Send
        </Button>
      </section>

      <section className="fb-card">
        <h2>Your feedback</h2>
        {mine.length === 0 ? (
          <EmptyState title="Nothing sent yet" text="Your ratings and messages will show here." />
        ) : (
          mine.map((e) => (
            <div className="fb-item" key={e.id}>
              <div className="fb-meta">
                <b>{KIND_TEXT[e.kind] || e.kind}</b>
                <Stars value={e.rating} />
                <span>{when(e.created_at)}</span>
              </div>
              {e.text && <p>{e.text}</p>}
              <Button kind="secondary" size="sm" onClick={() => setDel(e.id)}>
                Delete
              </Button>
            </div>
          ))
        )}
      </section>

      {del !== null && (
        <ConfirmDialog
          title="Delete this feedback?"
          text="This cannot be undone."
          confirm="Delete"
          danger
          onYes={() => remove(del)}
          onNo={() => setDel(null)}
        />
      )}
    </div>
  );
}

function Owner() {
  const [sum, setSum] = useState(null);
  const [list, setList] = useState(null);
  const [err, setErr] = useState("");
  const [note, setNote] = useState(null);
  const [tick, setTick] = useState(0);
  const [kind, setKind] = useState("");
  const [unread, setUnread] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    let live = true;
    const qs = "?page=" + page + (kind ? "&kind=" + kind : "") + (unread ? "&unread=1" : "");
    Promise.all([call("/api/feedback/summary/"), call("/api/feedback/all/" + qs)])
      .then(([s, l]) => {
        if (live) {
          setSum(s);
          setList(l);
          setErr("");
        }
      })
      .catch((e) => {
        if (live) setErr(e.message);
      });
    return () => {
      live = false;
    };
  }, [tick, kind, unread, page]);

  const refresh = () => setTick((t) => t + 1);

  const mark = async (e) => {
    setNote(null);
    try {
      await call("/api/feedback/" + e.id + "/read/", "POST", { read: !e.is_read });
      refresh();
    } catch (x) {
      setNote({ kind: "err", text: x.message });
    }
  };

  if (!list && !err) return <Loading />;
  if (!list || !sum) return <ErrorState text={err || "Could not load feedback."} onRetry={refresh} />;

  const pages = Math.max(1, Math.ceil(list.count / list.page_size));
  const byStar = [5, 4, 3, 2, 1].map((n) => n + STAR + " " + sum.by_star[String(n)]).join("   ");

  return (
    <div className="fb-wrap">
      {note && <Alert kind={note.kind}>{note.text}</Alert>}
      <div className="fb-grid">
        <StatCard
          label="Average rating"
          value={sum.average === null ? "None yet" : sum.average + " / 5"}
          note={
            sum.ratings +
            (sum.ratings === 1 ? " rating" : " ratings") +
            " from " +
            sum.schools +
            (sum.schools === 1 ? " school" : " schools")
          }
        />
        <StatCard label="Unread" value={sum.unread} note={sum.total + " in total"} />
      </div>
      {sum.ratings > 0 && <p className="plain">{byStar}</p>}

      <div className="fb-filters">
        <Select
          label="Type"
          value={kind}
          onChange={(e) => {
            setKind(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All types</option>
          {Object.keys(KIND_TEXT).map((k) => (
            <option key={k} value={k}>
              {KIND_TEXT[k]}
            </option>
          ))}
        </Select>
        <Select
          label="Show"
          value={unread}
          onChange={(e) => {
            setUnread(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All</option>
          <option value="1">Unread only</option>
        </Select>
      </div>

      <section className="fb-card">
        {list.results.length === 0 ? (
          <EmptyState title="Nothing here" text="No feedback matches this filter." />
        ) : (
          list.results.map((e) => (
            <div className={"fb-item" + (e.is_read ? "" : " fb-new")} key={e.id}>
              <div className="fb-meta">
                <b>{KIND_TEXT[e.kind] || e.kind}</b>
                <Stars value={e.rating} />
                <span>{when(e.created_at)}</span>
              </div>
              <div className="fb-meta">
                <span>
                  {e.author}
                  {e.role ? ", " + e.role : ""}
                  {e.school ? ", " + e.school : ""}
                </span>
              </div>
              {e.text && <p>{e.text}</p>}
              <Button kind="secondary" size="sm" onClick={() => mark(e)}>
                {e.is_read ? "Mark unread" : "Mark read"}
              </Button>
            </div>
          ))
        )}
      </section>

      <div className="fb-pager">
        <Button kind="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
          Previous
        </Button>
        <span>{"Page " + page + " of " + pages}</span>
        <Button kind="secondary" size="sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
          Next
        </Button>
      </div>
    </div>
  );
}

export default function Feedback({ owner }) {
  return owner ? <Owner /> : <Member />;
}
