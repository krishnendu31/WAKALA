// Light-theme colours for SVG libraries (Recharts, React Flow) that need literal values.
// Keep in sync with the @theme tokens in styles/index.css.
export const CHART = {
  grid: "#e0e4e3",
  tick: "#687783",
  tickStrong: "#1d3040",
  cursor: "#193e600d",
  tooltip: { background: "#ffffff", border: "1px solid #e0e4e3", borderRadius: 10, fontSize: 12, boxShadow: "0 6px 20px -12px #1d304033", color: "#1d3040" },
  tooltipLabel: { color: "#1d3040", fontWeight: 600 },
  emerald: "#0e4d48",
  navy: "#193e60",
  gold: "#b48a55",
  plan: "#4b5c9e",
  steel: "#8ca2c4",
  warn: "#a85a06",
  deny: "#b42318",
  neutral: "#9aa6ad",
  surface: "#ffffff",
  dots: "#d5dbda",
} as const;
