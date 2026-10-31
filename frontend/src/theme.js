const KEY = 'marian-theme'; // 'mixed' | 'dark'
export const applyTheme = (t) => document.documentElement.setAttribute('data-theme', t === 'dark' ? 'dark' : 'mixed');
export const getTheme = () => { try { return localStorage.getItem(KEY) === 'dark' ? 'dark' : 'mixed'; } catch { return 'mixed'; } };
export const setTheme = (t) => { try { localStorage.setItem(KEY, t === 'dark' ? 'dark' : 'mixed'); } catch { /* storage unavailable */ } applyTheme(t); };
export const initTheme = () => applyTheme(getTheme());
