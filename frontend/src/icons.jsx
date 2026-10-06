const P = {
  Home: "M3 11l9-8 9 8v10h-6v-6H9v6H3z",
  Approve: "M5 12l5 5 9-10",
  Exams: "M6 3h9l4 4v14H6z M9 13h6 M9 17h6",
  Reports: "M8 4h8v3H8z M6 5H5v16h14V5h-1 M9 12h6 M9 16h4",
  Analytics: "M4 20V10 M10 20V4 M16 20v-7 M2 20h20",
  Marks: "M4 20l1-4L16 5l3 3L8 19z",
  Bell: "M6 9a6 6 0 0 1 12 0c0 6 3 7 3 7H3s3-1 3-7 M10 20a2 2 0 0 0 4 0",
  Search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z M21 21l-5-5",
  More: "M5 12h.01 M12 12h.01 M19 12h.01",
  Students: "M3 21v-2a4 4 0 0 1 4-4h6a4 4 0 0 1 4 4v2 M10 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  Teachers: "M2 8l10-4 10 4-10 4z M6 10v5c0 1.5 3 3 6 3s6-1.5 6-3v-5",
  Setup: "M4 7h9 M17 7h3 M4 17h3 M11 17h9 M15 4v6 M7 14v6",
  Schools: "M3 21h18 M5 21V7l7-4 7 4v14 M9 21v-6h6v6 M9 10h.01 M15 10h.01",
  Admins: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z M9 12l2 2 4-4",
};
export default function Ic({ n, size = 20 }) {
  return (<svg viewBox="0 0 24 24" width={size} height={size} fill="none"
    stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
    strokeLinejoin="round" aria-hidden="true"><path d={P[n] || P.More} /></svg>);
}
