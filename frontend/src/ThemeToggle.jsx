import { useState } from 'react';
import { getTheme, setTheme } from './theme';

export default function ThemeToggle() {
  const [t, setT] = useState(getTheme());
  const dark = t === 'dark';
  const flip = () => {
    const next = dark ? 'mixed' : 'dark';
    setTheme(next);
    setT(next);
  };
  return (
    <button type="button" className="m-theme-btn" aria-pressed={dark} aria-label="Dark theme" onClick={flip}>
      <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></svg>
    </button>
  );
}
