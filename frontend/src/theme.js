const KEY = "marian-theme"; // "auto" | "light" | "dark"
export const applyTheme = (t) => document.documentElement.setAttribute("data-theme", t);
export const getTheme = () => { try { return localStorage.getItem(KEY) || "dark"; } catch { return "dark"; } };
export const setTheme = (t) => { try { localStorage.setItem(KEY, t); } catch {} applyTheme(t); };
export const initTheme = () => applyTheme(getTheme());
