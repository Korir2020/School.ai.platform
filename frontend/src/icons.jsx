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
  Teachers: "M3 21v-2a4 4 0 0 1 4-4h6a4 4 0 0 1 4 4v2 M10 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  Students: "M2 8l10-4 10 4-10 4z M6 10v5c0 1.5 3 3 6 3s6-1.5 6-3v-5",
  Setup: "M4 7h9 M17 7h3 M4 17h3 M11 17h9 M15 4v6 M7 14v6",
  Schools: "M3 21h18 M5 21V7l7-4 7 4v14 M9 21v-6h6v6 M9 10h.01 M15 10h.01",
  Admins: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z M9 12l2 2 4-4",
  Fees: "M4 6h16v12H4z M8 10h8 M8 14h5",
  Attendance: "M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z M8 3v4 M16 3v4 M4 10h16 M9 15l2 2 4-4",
  Documents: "M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z M14 3v5h5 M9 13h6 M9 17h6",
  Parents: "M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M3 20v-1a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v1 M17 11a2.2 2.2 0 1 0 0-4.4 2.2 2.2 0 0 0 0 4.4z M17.5 15.2a3.5 3.5 0 0 1 3.5 3.3V20",
  Transfers: "M4 8h14 M14 4l4 4-4 4 M20 16H6 M10 12l-4 4 4 4",
  Staff: "M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6z M12 11a2 2 0 1 0 0-4 2 2 0 0 0 0 4z M8.5 17a3.5 3.5 0 0 1 7 0",
  Audit: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8 M3 3v5h5 M12 7v5l4 2",
  Registrations: "M16 20v-1a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v1 M10 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z M19 8v6 M16 11h6",
  Enrollments: "M15 20v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2 M9 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6 M19 8v6 M16 11h6",
  Streams: "M12 3l9 5-9 5-9-5z M3 13l9 5 9-5",
  Subjects: "M4 4h6a2 2 0 0 1 2 2v14a2 2 0 0 0-2-2H4z M20 4h-6a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h6z",
  Help: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.5 M12 17h.01",
  Logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4 M16 17l5-5-5-5 M21 12H9",
  Trophy: "M8 21h8 M12 17v4 M7 4h10v5a5 5 0 0 1-10 0z M7 6H4v1a3 3 0 0 0 3 3 M17 6h3v1a3 3 0 0 1-3 3",
  Alert: "M12 3l10 18H2z M12 10v5 M12 18h.01",
  Clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 7v5l3 2",
};
export default function Ic({ n, size = 20 }) {
  return (<svg viewBox="0 0 24 24" width={size} height={size} fill="none"
    stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
    strokeLinejoin="round" aria-hidden="true"><path d={P[n] || P.More} /></svg>);
}
