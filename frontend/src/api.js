const BASE = import.meta.env.VITE_API_URL || "";
const J = { "Content-Type": "application/json" };
let access = null, inflight = null;
const mark = (on) => {
  try {
    if (on) localStorage.setItem("in", "1");
    else localStorage.removeItem("in");
  } catch (e) {}
};
try {
  localStorage.removeItem("access");
  localStorage.removeItem("refresh");
} catch (e) {}
const post = (path, body) => fetch(`${BASE}${path}`, {
  method: "POST", headers: J, body: JSON.stringify(body),
  credentials: "include",
});

export async function login(username, password) {
  const r = await post("/api/auth/login/", { username, password });
  if (r.status === 429) {
    throw new Error("Too many attempts. Wait a minute and try again.");
  }
  if (!r.ok) throw new Error("Wrong username or password");
  access = (await r.json()).access;
  mark(true);
}

function refresh() {
  inflight = inflight || post("/api/auth/refresh/", {})
    .then(async (r) => {
      if (r.ok) { access = (await r.json()).access; return true; }
      if (r.status === 401 || r.status === 400) {
        access = null;
        mark(false);
      }
      return false;
    })
    .catch(() => false)
    .finally(() => { inflight = null; });
  return inflight;
}

export async function api(path, method = "GET", body) {
  const run = () => fetch(`${BASE}${path}`, {
    method,
    headers: { ...J, Authorization: `Bearer ${access}` },
    body: body ? JSON.stringify(body) : undefined,
    credentials: "include",
  });
  if (!access) await refresh();
  let r = await run();
  if (r.status === 401 && (await refresh())) r = await run();
  return r;
}

export async function logout() {
  try { await post("/api/auth/logout/", {}); } catch (e) {}
  access = null;
  mark(false);
}

// Fetch every page of a list endpoint (also accepts plain arrays).
export async function listAll(path) {
  const sep = path.includes("?") ? "&" : "?";
  let url = `${path}${sep}page_size=200`;
  const out = [];
  for (let i = 0; i < 200 && url; i++) {
    const r = await api(url);
    if (!r.ok) return out;
    const d = await r.json();
    if (Array.isArray(d)) return d;
    out.push(...(d.results || []));
    if (!d.next) break;
    const n = new URL(d.next, "http://x");
    url = `${n.pathname}${n.search}`;
  }
  return out;
}
