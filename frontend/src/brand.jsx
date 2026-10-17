export function Mark({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="#1e9a68" />
    <path d="M9 23.5V9.5L16 17L23 9.5V23.5M13 23.5V20M19 23.5V20" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Wordmark({ height = 16 }) {
  return (
    <svg height={height} width={(height * 168) / 36} viewBox="0 0 168 36"
      role="img" aria-label="MARIAN" fill="none" stroke="currentColor"
      strokeWidth="6" strokeLinejoin="bevel">
      <path d="M3 32V4L14.5 20L26 4V32" />
      <path d="M33 32L46 4L59 32" />
      <path d="M66 32V4H78Q88 4 88 12.5Q88 21 78 21H66M77 21L89 32" />
      <path d="M97 4V32" />
      <path d="M106 32L119 4L132 32" />
      <path d="M140 32V4L162 32V4" />
    </svg>
  );
}
