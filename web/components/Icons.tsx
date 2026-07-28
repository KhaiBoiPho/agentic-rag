import type { SVGProps } from "react";

const base = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

type P = SVGProps<SVGSVGElement>;

export const Logo = (p: P) => (
  <svg {...base} strokeWidth={1.7} {...p}>
    <path d="M4 21V6l8-3 8 3v15" />
    <path d="M4 21h16M9 21v-6h6v6M8 9h.01M12 9h.01M16 9h.01" />
  </svg>
);
export const Chat = (p: P) => (
  <svg {...base} {...p}>
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </svg>
);
// Chatbot mark — a friendly robot head (antenna + rounded head + two eyes).
// Uses currentColor so it inverts with the theme wherever it's placed.
export const Bot = (p: P) => (
  <svg {...base} {...p}>
    <path d="M12 4.2v3.3" />
    <circle cx="12" cy="3.2" r="1.15" />
    <rect x="4" y="7.5" width="16" height="11" rx="3.6" />
    <path d="M2 12.5v2.4M22 12.5v2.4" />
    <circle cx="9" cy="12.9" r="1.15" fill="currentColor" stroke="none" />
    <circle cx="15" cy="12.9" r="1.15" fill="currentColor" stroke="none" />
  </svg>
);
export const Note = (p: P) => (
  <svg {...base} {...p}>
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <path d="M14 2v6h6M9 13h6M9 17h4" />
  </svg>
);
export const Folder = (p: P) => (
  <svg {...base} {...p}>
    <path d="M3 7h6l2 2h10v10a2 2 0 0 1-2 2H3z" />
  </svg>
);
export const Book = (p: P) => (
  <svg {...base} {...p}>
    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
  </svg>
);
export const Chart = (p: P) => (
  <svg {...base} {...p}>
    <path d="M3 3v18h18" />
    <path d="M7 14l3-3 3 3 5-6" />
  </svg>
);
export const Gear = (p: P) => (
  <svg {...base} {...p}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 13a7 7 0 0 0 0-2l2-1.5-2-3.4-2.4 1a7 7 0 0 0-1.7-1L14.9 3h-4l-.4 2.6a7 7 0 0 0-1.7 1l-2.4-1-2 3.4L6.6 11a7 7 0 0 0 0 2l-2 1.5 2 3.4 2.4-1a7 7 0 0 0 1.7 1l.4 2.6h4l.4-2.6a7 7 0 0 0 1.7-1l2.4 1 2-3.4z" />
  </svg>
);
export const Search = (p: P) => (
  <svg {...base} {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="m21 21-4.3-4.3" />
  </svg>
);
export const Globe = (p: P) => (
  <svg {...base} {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M2 12h20M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18" />
  </svg>
);
export const Mic = (p: P) => (
  <svg {...base} {...p}>
    <rect x="9" y="2" width="6" height="12" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </svg>
);
export const Send = (p: P) => (
  <svg {...base} {...p}>
    <path d="M22 2 11 13M22 2l-7 20-4-9-9-4z" />
  </svg>
);
export const Sheet = (p: P) => (
  <svg {...base} {...p}>
    <rect x="4" y="2" width="16" height="20" rx="2" />
    <path d="M8 6h8M8 10h8M8 14h5" />
  </svg>
);
export const Warn = (p: P) => (
  <svg {...base} {...p}>
    <path d="M12 9v4M12 17h.01" />
    <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
  </svg>
);
export const Sun = (p: P) => (
  <svg {...base} {...p}>
    <circle cx="12" cy="12" r="4.5" />
    <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" />
  </svg>
);
export const Menu = (p: P) => (
  <svg {...base} {...p}>
    <path d="M3 6h18M3 12h18M3 18h18" />
  </svg>
);
export const Plus = (p: P) => (
  <svg {...base} {...p}>
    <path d="M12 5v14M5 12h14" />
  </svg>
);
export const Trash = (p: P) => (
  <svg {...base} {...p}>
    <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
  </svg>
);
export const Logout = (p: P) => (
  <svg {...base} {...p}>
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
  </svg>
);
export const Upload = (p: P) => (
  <svg {...base} {...p}>
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12" />
  </svg>
);
export const Check = (p: P) => (
  <svg {...base} {...p}>
    <path d="M20 6 9 17l-5-5" />
  </svg>
);
export const Loader = (p: P) => (
  <svg {...base} {...p}>
    <path d="M21 12a9 9 0 1 1-6.2-8.6" />
  </svg>
);
export const Pin = (p: P) => (
  <svg {...base} {...p}>
    <path d="M12 17v5" />
    <path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z" />
  </svg>
);
export const PanelLeft = (p: P) => (
  <svg {...base} {...p}>
    <rect x="3" y="4" width="18" height="16" rx="2.5" />
    <path d="M9.5 4v16" />
  </svg>
);
