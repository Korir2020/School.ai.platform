import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, upload } from "./api";
import { Alert, Button, ConfirmDialog, EmptyState, ErrorState, Loading, Select } from "./ui";
import "./connect.css";

const MAX = 2000;
const POLL_MS = 20000;
const ROLE_TEXT = { admin: "School admin", teacher: "Teacher" };

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
  return new Date(iso).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function day(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" });
}

function mergeFeed(prev, d) {
  if (!d.has_more) return { posts: d.posts, hasMore: false };
  const floor = d.posts.length ? d.posts[d.posts.length - 1].id : 0;
  const older = prev.posts.filter((p) => p.id < floor);
  return { posts: d.posts.concat(older), hasMore: older.length ? prev.hasMore : true };
}

const AV_CACHE = new Map();

function AuthorAv({ post }) {
  const key = post.id + ":" + post.author_pic;
  const [src, setSrc] = useState(post.author_pic ? AV_CACHE.get(key) || "" : "");
  useEffect(() => {
    if (!post.author_pic) return undefined;
    if (AV_CACHE.has(key)) {
      setSrc(AV_CACHE.get(key));
      return undefined;
    }
    let alive = true;
    api("/api/connect/posts/" + post.id + "/avatar/")
      .then(async (r) => {
        if (!r.ok) return;
        const url = URL.createObjectURL(await r.blob());
        AV_CACHE.set(key, url);
        if (alive) setSrc(url);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [key, post.id, post.author_pic]);
  return (
    <span className="cn-av" aria-hidden="true">
      {post.author_pic && src ? (
        <img src={src} alt="" />
      ) : (
        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7z" /></svg>
      )}
    </span>
  );
}

function PostCard({ post, me, acts }) {
  const [open, setOpen] = useState(false);
  const timer = useRef(null);
  const pressAt = useRef({ x: 0, y: 0 });
  const admin = me.is_admin;
  const hasMenu = !post.mine || post.can_delete || admin;
  const pressStart = (e) => {
    if (!hasMenu || e.target.closest("a,button,video,audio")) return;
    pressAt.current = { x: e.clientX, y: e.clientY };
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setOpen(true), 500);
  };
  const pressMove = (e) => {
    if (Math.abs(e.clientX - pressAt.current.x) > 8 || Math.abs(e.clientY - pressAt.current.y) > 8) clearTimeout(timer.current);
  };
  const pressEnd = () => clearTimeout(timer.current);
  const menuOnRight = (e) => {
    if (!hasMenu || e.target.closest("a,video,audio")) return;
    e.preventDefault();
    clearTimeout(timer.current);
    setOpen(true);
  };
  const roleText = ROLE_TEXT[post.author_role];
  const cls = "cn-post" + (post.is_urgent ? " urgent" : "") + (post.hidden ? " hidden" : "");
  return (
    <article onPointerDown={pressStart} onPointerMove={pressMove} onPointerUp={pressEnd} onPointerCancel={pressEnd} onPointerLeave={pressEnd} onContextMenu={menuOnRight} className={cls + (post.mine ? " mine" : "")}>
      <header className="cn-ph">
        <AuthorAv post={post} />
        <b>{post.author}</b>
        {roleText && <span className="cn-tag">{roleText}</span>}
        {post.is_urgent && <span className="cn-tag cn-urgent">Urgent</span>}
        {post.is_pinned && <span className="cn-tag">Pinned</span>}
        {post.hidden && <span className="cn-tag cn-urgent">Hidden</span>}
        <time className="cn-time" dateTime={post.created_at}>{when(post.created_at)}</time>
      </header>
      {post.body && <p className="cn-body">{post.body}</p>}
      {post.attachments && post.attachments.length > 0 && (
        <div className="cn-atts">
          {post.attachments.map((a) => (
            <AttachmentView key={a.id} att={a} />
          ))}
        </div>
      )}
      {post.event && (
        <p className="cn-event">
          <b>{post.event.title}</b> {day(post.event.start_date)}
          {post.event.end_date ? " to " + day(post.event.end_date) : ""}
        </p>
      )}
      {admin && post.report_count > 0 && (
        <div className="cn-pa">
          <span className="cn-tag cn-urgent">
            {post.report_count} {post.report_count === 1 ? "report" : "reports"}
          </span>
        </div>
      )}
      {open && hasMenu && (
        <div className="cn-menu" role="menu">
          {!post.mine && <button type="button" role="menuitem" className="cn-link" onClick={() => { setOpen(false); acts.report(post); }}>Report</button>}
          {post.can_delete && <button type="button" role="menuitem" className="cn-link" onClick={() => { setOpen(false); acts.remove(post); }}>Delete</button>}
          {admin && (
            <>
              <button type="button" role="menuitem" className="cn-link" onClick={() => { setOpen(false); acts.patch(post, { is_pinned: !post.is_pinned }); }}>{post.is_pinned ? "Unpin" : "Pin"}</button>
              <button type="button" role="menuitem" className="cn-link" onClick={() => { setOpen(false); acts.patch(post, { is_urgent: !post.is_urgent }); }}>{post.is_urgent ? "Clear urgent" : "Mark urgent"}</button>
              <button type="button" role="menuitem" className="cn-link" onClick={() => { setOpen(false); acts.patch(post, { hidden: !post.hidden }); }}>{post.hidden ? "Show again" : "Hide from members"}</button>
            </>
          )}
          <button type="button" className="cn-link" onClick={() => setOpen(false)}>Close</button>
        </div>
      )}
    </article>
  );
}

const MAX_FILES = 4;
const MAX_BYTES = 5 * 1024 * 1024;

function sizeText(n) {
  return n < 1048576 ? Math.max(1, Math.round(n / 1024)) + " KB" : (n / 1048576).toFixed(1) + " MB";
}

function Ic({ children }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  );
}

async function shrink(file) {
  if (file.type.indexOf("image/") !== 0 || file.type === "image/gif") return file;
  try {
    const bmp = await createImageBitmap(file);
    const scale = Math.min(1, 1600 / Math.max(bmp.width, bmp.height));
    const w = Math.round(bmp.width * scale);
    const h = Math.round(bmp.height * scale);
    const c = document.createElement("canvas");
    c.width = w;
    c.height = h;
    const g = c.getContext("2d");
    g.fillStyle = "#fff";
    g.fillRect(0, 0, w, h);
    g.drawImage(bmp, 0, 0, w, h);
    const blob = await new Promise((res) => c.toBlob(res, "image/jpeg", 0.82));
    if (!blob || blob.size >= file.size) return file;
    return new File([blob], file.name.replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" });
  } catch {
    return file;
  }
}

function AttachmentView({ att }) {
  const isImg = att.type.indexOf("image/") === 0;
  const path = "/api/connect/attachments/" + att.id + "/";
  const [src, setSrc] = useState("");
  const [big, setBig] = useState(false);
  const [bad, setBad] = useState(false);

  useEffect(() => {
    if (!isImg) return undefined;
    let alive = true;
    let url = "";
    api(path)
      .then(async (r) => {
        if (!r.ok) throw new Error("load");
        url = URL.createObjectURL(await r.blob());
        if (alive) setSrc(url);
      })
      .catch(() => {
        if (alive) setBad(true);
      });
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [path, isImg]);

  const download = async () => {
    setBad(false);
    try {
      const r = await api(path);
      if (!r.ok) throw new Error("load");
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = att.name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch {
      setBad(true);
    }
  };

  if (isImg) {
    if (bad) return <span className="cn-meta">Could not load photo.</span>;
    if (!src) return <span className="cn-meta">Loading photo...</span>;
    return (
      <>
        <button type="button" className="cn-img" onClick={() => setBig(true)} aria-label={"Open photo " + att.name}>
          <img src={src} alt={att.name} />
        </button>
        {big && (
          <button type="button" className="cn-lightbox" onClick={() => setBig(false)} aria-label="Close photo">
            <img src={src} alt={att.name} />
          </button>
        )}
      </>
    );
  }
  return (
    <>
      <button type="button" className="cn-file" onClick={download}>
        <Ic>
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <path d="M14 2v6h6" />
        </Ic>
        <span>{att.name} - {sizeText(att.size)}</span>
      </button>
      {bad && <span className="cn-meta">Could not open file.</span>}
    </>
  );
}

function Thumb({ file, onRemove }) {
  const url = useMemo(() => (file.type.indexOf("image/") === 0 ? URL.createObjectURL(file) : ""), [file]);
  useEffect(() => {
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [url]);
  return (
    <div className="cn-thumb">
      {url ? <img src={url} alt={file.name} /> : <span className="cn-doc">{file.name}</span>}
      <button type="button" className="cn-x" aria-label={"Remove " + file.name} onClick={onRemove}>x</button>
    </div>
  );
}

function Composer({ me, events, onSend, onDone }) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState([]);
  const [urgent, setUrgent] = useState(false);
  const [pin, setPin] = useState(false);
  const [eventId, setEventId] = useState("");
  const [more, setMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const pick = useRef(null);
  const box = useRef(null);

  const add = async (list) => {
    setErr("");
    const chosen = Array.from(list);
    const room = MAX_FILES - files.length;
    if (chosen.length > room) setErr("You can attach up to " + MAX_FILES + " files to one message.");
    const next = [];
    for (const f of chosen.slice(0, Math.max(room, 0))) {
      const g = await shrink(f);
      if (g.size > MAX_BYTES) {
        setErr(f.name + " is larger than 5 MB.");
        continue;
      }
      next.push(g);
    }
    if (next.length) setFiles((prev) => [...prev, ...next].slice(0, MAX_FILES));
  };

  const send = async () => {
    if (busy) return;
    if (!text.trim() && files.length === 0) return;
    setBusy(true);
    setErr("");
    const fd = new FormData();
    fd.append("body", text);
    if (me.is_admin) {
      fd.append("is_urgent", urgent ? "true" : "false");
      fd.append("is_pinned", pin ? "true" : "false");
      if (eventId) fd.append("event_id", eventId);
    }
    files.forEach((f) => fd.append("files", f, f.name));
    try {
      const r = await onSend(fd);
      if (!r.ok) {
        let m = "";
        try {
          m = (await r.json()).message;
        } catch {
          m = "";
        }
        throw new Error(m || "Something went wrong. Please try again.");
      }
      setText("");
      setFiles([]);
      setUrgent(false);
      setPin(false);
      setEventId("");
      setMore(false);
      if (box.current) box.current.style.height = "auto";
      onDone();
    } catch (e) {
      setErr(e.name === "TimeoutError" ? "The upload took too long. Check your connection and try again." : e.message);
    }
    setBusy(false);
  };

  return (
    <div className="cn-bar">
      {err && <Alert kind="err">{err}</Alert>}
      {me.is_admin && more && (
        <div className="cn-more">
          <label className="cn-check">
            <input type="checkbox" checked={urgent} onChange={(e) => setUrgent(e.target.checked)} />
            Mark as urgent
          </label>
          <label className="cn-check">
            <input type="checkbox" checked={pin} onChange={(e) => setPin(e.target.checked)} />
            Pin to the top
          </label>
          <Select label="Attach a calendar event" value={eventId} onChange={(e) => setEventId(e.target.value)}>
            <option value="">None</option>
            {events.map((ev) => (
              <option key={ev.id} value={ev.id}>{ev.title + " (" + day(ev.start_date) + ")"}</option>
            ))}
          </Select>
        </div>
      )}
      {files.length > 0 && (
        <div className="cn-files">
          {files.map((f, i) => (
            <Thumb key={f.name + i + f.size} file={f} onRemove={() => setFiles((prev) => prev.filter((_, j) => j !== i))} />
          ))}
        </div>
      )}
      <div className="cn-row2">
        <input
          ref={pick}
          type="file"
          multiple
          hidden
          accept="image/*,.pdf,.doc,.docx,.xls,.xlsx"
          onChange={(e) => {
            add(e.target.files);
            e.target.value = "";
          }}
        />
        <button type="button" className="cn-ic" aria-label="Attach files" disabled={files.length >= MAX_FILES} onClick={() => pick.current && pick.current.click()}>
          <Ic><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48" /></Ic>
        </button>
        {me.is_admin && (
          <button type="button" className="cn-ic" aria-label="Post options" aria-expanded={more} onClick={() => setMore(!more)}>
            <Ic><circle cx="5" cy="12" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /></Ic>
          </button>
        )}
        <textarea
          ref={box}
          className="cn-msg"
          rows={1}
          maxLength={MAX}
          placeholder="Type a message..."
          aria-label="Message"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            e.target.style.height = "auto";
            e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
          }}
        />
        <button type="button" className="cn-send" aria-label="Send" disabled={busy || (!text.trim() && files.length === 0)} onClick={send}>
          <Ic><path d="m22 2-7 20-4-9-9-4z" /><path d="M22 2 11 13" /></Ic>
        </button>
      </div>
    </div>
  );
}

function ChatPanel({ channel, me, onSeen }) {
  const [feed, setFeed] = useState({ posts: [], hasMore: false });
  const [pinned, setPinned] = useState([]);
  const [canPost, setCanPost] = useState(false);
  const [ready, setReady] = useState(false);
  const [err, setErr] = useState("");
  const [note, setNote] = useState(null);
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [events, setEvents] = useState([]);
  const [pending, setPending] = useState(null);
  const [loadingMore, setLoadingMore] = useState(false);

  const base = "/api/connect/channels/" + channel.id + "/posts/";

  const refresh = useCallback(async () => {
    const qs = new URLSearchParams({ limit: "30" });
    if (query) qs.set("q", query);
    try {
      const d = await call(base + "?" + qs);
      setFeed((prev) => mergeFeed(prev, d));
      setPinned(d.pinned);
      setCanPost(d.can_post);
      setErr("");
      setReady(true);
      if (!query) onSeen();
    } catch (e) {
      setErr(e.message);
    }
  }, [base, query, onSeen]);

  useEffect(() => {
    const first = setTimeout(() => {
      refresh();
    }, 0);
    const t = setInterval(() => {
      if (!document.hidden) refresh();
    }, POLL_MS);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
  }, [refresh]);

  useEffect(() => {
    if (!me.is_admin) return undefined;
    let alive = true;
    const from = new Date();
    const to = new Date(from.getTime() + 90 * 86400000);
    const iso = (x) => x.toISOString().slice(0, 10);
    call("/api/calendar/events/?from=" + iso(from) + "&to=" + iso(to))
      .then((d) => {
        if (alive) setEvents(d.events);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [me.is_admin]);

  const act = async (fn, okText) => {
    setNote(null);
    try {
      await fn();
      if (okText) setNote({ kind: "info", text: okText });
      await refresh();
    } catch (e) {
      setNote({ kind: "err", text: e.message });
    }
  };

  const runPending = async () => {
    const c = pending;
    setPending(null);
    if (c) await act(c.run, c.ok);
  };

  const acts = {
    ack: (p) => act(() => call("/api/connect/posts/" + p.id + "/ack/", "POST")),
    patch: (p, body) => act(() => call("/api/connect/posts/" + p.id + "/", "PATCH", body)),
    report: (p) =>
      setPending({
        title: "Report this post?",
        text: "The school administrators will review it. Your name is not shown to them.",
        confirm: "Report",
        ok: "Reported. Thank you.",
        run: () => call("/api/connect/posts/" + p.id + "/report/", "POST", {}),
      }),
    remove: (p) =>
      setPending({
        title: "Delete this post?",
        text: "This permanently deletes the post. It cannot be undone.",
        confirm: "Delete",
        danger: true,
        run: () => call("/api/connect/posts/" + p.id + "/", "DELETE"),
      }),
  };

  const startSearch = (e) => {
    e.preventDefault();
    setFeed({ posts: [], hasMore: false });
    setReady(false);
    setQuery(draft.trim());
  };

  const clearSearch = () => {
    setDraft("");
    setFeed({ posts: [], hasMore: false });
    setReady(false);
    setQuery("");
  };

  const loadEarlier = async () => {
    const last = feed.posts[feed.posts.length - 1];
    if (!last) return;
    setLoadingMore(true);
    try {
      const qs = new URLSearchParams({ limit: "30", before: String(last.id) });
      if (query) qs.set("q", query);
      const d = await call(base + "?" + qs);
      setFeed((prev) => ({ posts: prev.posts.concat(d.posts), hasMore: d.has_more }));
    } catch (e) {
      setNote({ kind: "err", text: e.message });
    }
    setLoadingMore(false);
  };

  const newestId = feed.posts.length ? feed.posts[0].id : 0;
  useEffect(() => {
    if (!ready) return undefined;
    const t = setTimeout(() => {
      const el = document.getElementById("cn-end");
      if (el) el.scrollIntoView({ block: "end" });
    }, 60);
    return () => clearTimeout(t);
  }, [ready, newestId]);

  if (!ready && !err) return <Loading />;
  const pinIds = new Set(query ? [] : pinned.map((p) => p.id));
  const shown = feed.posts.filter((p) => !pinIds.has(p.id));

  return (
    <div className="cn-chat">
      {err && <ErrorState text={err} onRetry={refresh} />}
      <form className="cn-search" onSubmit={startSearch}>
        <input
          type="search"
          value={draft}
          maxLength={60}
          placeholder="Search this channel"
          aria-label="Search this channel"
          onChange={(e) => setDraft(e.target.value)}
        />
        <Button kind="secondary" size="sm" type="submit">Search</Button>
        {query && <Button kind="secondary" size="sm" onClick={clearSearch}>Clear</Button>}
      </form>
      {note && <Alert kind={note.kind}>{note.text}</Alert>}
      {!canPost && (
        <p className="cn-hint">
          {me.muted ? "You have been muted by a school administrator." : "Only school administrators post in this channel."}
        </p>
      )}
      {pinIds.size > 0 && (
        <section aria-label="Pinned posts">
          <h3 className="cn-h">Pinned</h3>
          {pinned.map((p) => (
            <PostCard key={"pin" + p.id} post={p} me={me} kind={channel.kind} acts={acts} />
          ))}
        </section>
      )}
      {query && <h3 className="cn-h">Search results</h3>}
      {feed.hasMore && (
          <Button kind="secondary" busy={loadingMore} onClick={loadEarlier}>Show earlier posts</Button>
        )}
        {shown.length === 0 && pinIds.size === 0 && (
        <EmptyState
          title={query ? "No matching posts" : "No posts yet"}
          text={query ? "Try a different word." : "Posts from the school will appear here."}
        />
      )}
      {[...shown].reverse().map((p) => (
        <PostCard key={p.id} post={p} me={me} kind={channel.kind} acts={acts} />
      ))}
      <div id="cn-end" />
        {canPost && (
          <Composer me={me} events={events} onSend={(fd) => upload(base, fd, 60000)} onDone={refresh} />
        )}
      {pending && (
        <ConfirmDialog
          title={pending.title}
          text={pending.text}
          confirm={pending.confirm}
          danger={pending.danger}
          onYes={runPending}
          onNo={() => setPending(null)}
        />
      )}
    </div>
  );
}

function MembersPanel({ me }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [applied, setApplied] = useState("");
  const [pending, setPending] = useState(null);

  const load = useCallback(async () => {
    try {
      const suffix = applied ? "?q=" + encodeURIComponent(applied) : "";
      setData(await call("/api/connect/members/" + suffix));
      setErr("");
    } catch (e) {
      setErr(e.message);
    }
  }, [applied]);

  useEffect(() => {
    const t = setTimeout(() => {
      load();
    }, 0);
    return () => clearTimeout(t);
  }, [load]);

  const setMute = async (m, on) => {
    try {
      await call("/api/connect/members/" + m.user_id + "/mute/", on ? "POST" : "DELETE");
      await load();
    } catch (e) {
      setErr(e.message);
    }
  };

  const runPending = async () => {
    const c = pending;
    setPending(null);
    if (c) await setMute(c.member, true);
  };

  if (err && !data) return <ErrorState text={err} onRetry={load} />;
  if (!data) return <Loading />;
  return (
    <div className="cn-members">
      {err && <Alert kind="err">{err}</Alert>}
      <p className="cn-hint">
        {data.parent_count + (data.parent_count === 1 ? " parent is" : " parents are")} in this group, each linked to a learner.
        {me.is_admin ? "" : " Parents' names are visible only to school administrators."}
      </p>
      {me.is_admin && (
        <form
          className="cn-search"
          onSubmit={(e) => {
            e.preventDefault();
            setApplied(q.trim());
          }}
        >
          <input
            type="search"
            value={q}
            maxLength={60}
            placeholder="Search parents by name"
            aria-label="Search parents by name"
            onChange={(e) => setQ(e.target.value)}
          />
          <Button kind="secondary" size="sm" type="submit">Search</Button>
        </form>
      )}
      {data.members.map((m) => (
        <div className="cn-row" key={(m.user_id || "s") + m.name + m.role}>
          <b>{m.name}</b>
          <span className="cn-tag">{ROLE_TEXT[m.role] || "Parent"}</span>
          {m.muted && <span className="cn-tag cn-urgent">Muted</span>}
          {me.is_admin && m.role !== "admin" && (
            m.muted
              ? <Button kind="secondary" size="sm" onClick={() => setMute(m, false)}>Unmute</Button>
              : <Button kind="secondary" size="sm" onClick={() => setPending({ member: m })}>Mute</Button>
          )}
        </div>
      ))}
      {data.truncated && <p className="cn-hint">Showing the first 100 parents. Use search to find others.</p>}
      {pending && (
        <ConfirmDialog
          title={"Mute " + pending.member.name + "?"}
          text="They can still read posts but cannot post until you unmute them."
          confirm="Mute"
          danger
          onYes={runPending}
          onNo={() => setPending(null)}
        />
      )}
    </div>
  );
}

function ReportsPanel() {
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const d = await call("/api/connect/reports/");
      setRows(d.reports);
      setErr("");
    } catch (e) {
      setErr(e.message);
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => {
      load();
    }, 0);
    return () => clearTimeout(t);
  }, [load]);

  const resolve = async (r, hide) => {
    try {
      await call("/api/connect/reports/" + r.id + "/resolve/", "POST", { hide });
      await load();
    } catch (e) {
      setErr(e.message);
    }
  };

  if (err && !rows) return <ErrorState text={err} onRetry={load} />;
  if (!rows) return <Loading />;
  if (rows.length === 0) return <EmptyState title="No open reports" text="Nothing needs your attention." />;
  return (
    <div>
      {err && <Alert kind="err">{err}</Alert>}
      {rows.map((r) => (
        <article className="cn-post urgent" key={r.id}>
          <header className="cn-ph">
            <b>{r.post.author}</b>
            <time className="cn-time" dateTime={r.post.created_at}>{when(r.post.created_at)}</time>
          </header>
          <p className="cn-body">{r.post.body}</p>
          {r.reason && <p className="cn-meta">{"Reason given: " + r.reason}</p>}
          <div className="cn-pa">
            <Button kind="secondary" size="sm" onClick={() => resolve(r, false)}>Dismiss</Button>
            <Button kind="teal" size="sm" onClick={() => resolve(r, true)}>Hide post</Button>
          </div>
        </article>
      ))}
    </div>
  );
}

export default function Connect() {
  const [boot, setBoot] = useState(null);
  const [bad, setBad] = useState("");
  const [channelId, setChannelId] = useState(null);
  const [view, setView] = useState("chat");

  const loadChannels = useCallback(async () => {
    try {
      const data = await call("/api/connect/channels/");
      setBoot(data);
      setBad("");
      setChannelId((cur) => (cur === null && data.channels.length ? data.channels[0].id : cur));
    } catch (e) {
      setBad(e.message);
    }
  }, []);

  useEffect(() => {
    const first = setTimeout(() => {
      loadChannels();
    }, 0);
    const t = setInterval(() => {
      if (!document.hidden) loadChannels();
    }, 30000);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
  }, [loadChannels]);

  if (bad && !boot) return <ErrorState text={bad} onRetry={loadChannels} />;
  if (!boot) return <Loading />;
  const { channels, me } = boot;
  const current = channels.find((c) => c.id === channelId) || channels[0];
  const tab = (on) => "cn-tab" + (on ? " on" : "");

  return (
    <div className="cn">
      <h2>Connect</h2>
      <p className="cn-hint">The school community space. Notices come from the school. Please keep posts respectful.</p>
      <nav className="cn-tabs" aria-label="Connect sections">
        {channels.map((c) => {
          const on = view === "chat" && current && current.id === c.id;
          return (
            <button
              key={c.id}
              type="button"
              className={tab(on)}
              aria-current={on ? "page" : undefined}
              onClick={() => {
                setChannelId(c.id);
            setView("chat");
              }}
            >
              {c.name}
              {c.unread > 0 && <span className="cn-badge">{c.unread}</span>}
            </button>
          );
        })}
        <button
          type="button"
          className={tab(view === "members")}
          aria-current={view === "members" ? "page" : undefined}
          onClick={() => setView("members")}
        >
          Members
        </button>
        {me.is_admin && (
          <button
            type="button"
            className={tab(view === "reports")}
            aria-current={view === "reports" ? "page" : undefined}
            onClick={() => setView("reports")}
          >
            Reports
          </button>
        )}
      </nav>
      {view === "chat" && current && <ChatPanel key={current.id} channel={current} me={me} onSeen={loadChannels} />}
      {view === "members" && <MembersPanel me={me} />}
      {view === "reports" && me.is_admin && <ReportsPanel />}
    </div>
  );
}
