import type { Config } from "tailwindcss";

// Design tokens from design/HANDOVER.md — reused verbatim from the mockup canvas and
// interactive prototype rather than reinvented (ticket #26).
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        ground: { light: "#F3F2EF", dark: "#0B0C0F" },
        indigo: { DEFAULT: "#6C7BFA", dark: "#8B97FC" },
        mint: "#7FF5CC",
        pink: "#FF8FCB",
        amber: { DEFAULT: "#A86F0C", dark: "#F5B942" },
        danger: "#F2555A",
      },
      fontFamily: {
        wordmark: ["Tiro Bangla", "serif"],
        heading: ["Space Grotesk", "sans-serif"],
        body: ["IBM Plex Sans", "sans-serif"],
        mono: ["IBM Plex Mono", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
