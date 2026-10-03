export default function Logo({ size = 64 }) {
  const bars = [[70, 52, 44], [86, 40, 56], [102, 28, 68]];
  return (
    <svg width={size} height={size * 0.9} viewBox="0 0 120 108" role="img" aria-label="Marian">
      <defs><linearGradient id="mg" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stopColor="#2563EB" /><stop offset=".55" stopColor="#06B6D4" /><stop offset="1" stopColor="#22C55E" />
      </linearGradient></defs>
      <path d="M6 10 L46 30 L46 86 Q26 82 6 90 Z" fill="url(#mg)" />
      <path d="M18 52 L46 66 L60 98 Q36 88 18 92 Z" fill="#06B6D4" opacity=".85" />
      {bars.map(([x, y, h], i) => <rect key={x} className="bar" style={{ animationDelay: 0.15 * i + "s" }} x={x} y={y} width="10" height={h} rx="1.5" fill="url(#mg)" />)}
      <path d="M62 56 L108 14" stroke="#06B6D4" strokeWidth="3" strokeLinecap="round" />
      <circle cx="72" cy="48" r="5" fill="#2563EB" /><circle cx="88" cy="33" r="5.5" fill="#06B6D4" /><circle cx="108" cy="14" r="6.5" fill="#22C55E" />
    </svg>
  );
}
