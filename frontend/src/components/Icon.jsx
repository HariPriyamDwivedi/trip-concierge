// Small inline icon set (24px grid, stroke-based) so the app needs no icon library.
const PATHS = {
  plane: "M2 16l20-7-20-7 4 7-4 7zM6 9h9",
  send: "M4 12l16-8-6 16-3-7-7-1z",
  clip: "M21 11l-8.5 8.5a5 5 0 01-7-7L14 4a3.5 3.5 0 015 5l-8.5 8.5a2 2 0 01-3-3L15 7",
  plus: "M12 5v14M5 12h14",
  file: "M14 3H6a1 1 0 00-1 1v16a1 1 0 001 1h12a1 1 0 001-1V8l-5-5zM14 3v5h5",
  book: "M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2V5zM4 19a2 2 0 002 2h13",
  globe: "M12 3a9 9 0 100 18 9 9 0 000-18zM3 12h18M12 3c3 3.5 3 14.5 0 18M12 3c-3 3.5-3 14.5 0 18",
  wallet: "M3 7h16a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V7zM3 7l12-4v4M16 13h2",
  pin: "M12 21s-7-6.1-7-11a7 7 0 0114 0c0 4.9-7 11-7 11zM12 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5z",
  bell: "M6 16V11a6 6 0 0112 0v5l2 2H4l2-2zM10 20a2 2 0 004 0",
  mail: "M3 6h18v12H3V6zM3 7l9 6 9-6",
  route: "M6 19a2 2 0 100-4 2 2 0 000 4zM18 9a2 2 0 100-4 2 2 0 000 4zM6 15V9a3 3 0 013-3h7M18 9v6a3 3 0 01-3 3H8",
  star: "M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9L12 3z",
  chat: "M4 5h16v11H8l-4 4V5z",
  train: "M7 3h10a3 3 0 013 3v8a3 3 0 01-3 3H7a3 3 0 01-3-3V6a3 3 0 013-3zM4 10h16M8 21l2-4M16 21l-2-4M8 14h.01M16 14h.01",
  bus: "M6 3h12a2 2 0 012 2v11H4V5a2 2 0 012-2zM4 10h16M7 19v2M17 19v2M7 13h.01M17 13h.01",
  bed: "M3 19v-9M21 19v-5a3 3 0 00-3-3H10v8M3 15h18M7 13a2 2 0 100-4 2 2 0 000 4z",
  trash: "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3",
  sun: "M12 8a4 4 0 100 8 4 4 0 000-8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
  camera: "M4 8h3l2-3h6l2 3h3a1 1 0 011 1v10a1 1 0 01-1 1H4a1 1 0 01-1-1V9a1 1 0 011-1zM12 17a4 4 0 100-8 4 4 0 000 8z",
  image: "M4 5h16v14H4V5zM4 15l4-4 4 4 3-3 5 5M15.5 9.5a1.5 1.5 0 100-3 1.5 1.5 0 000 3z",
  logout: "M15 4h4v16h-4M10 17l5-5-5-5M15 12H4",
  plug: "M9 3v5M15 3v5M6 8h12v3a6 6 0 01-12 0V8zM12 17v4",
  calendar: "M4 6h16v14H4V6zM4 10h16M8 3v5M16 3v5",
};

export default function Icon({ name, size = 18, className }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
