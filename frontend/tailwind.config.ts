import type { Config } from "tailwindcss";

/**
 * USWDS-aligned Tailwind config.
 *
 * We mirror a subset of USWDS color tokens (calm blues, neutral grays, status
 * semantics) and the 8px-based spacing scale, rather than pulling the full
 * USWDS library. See docs/tradeoffs.md "React + Vite + TypeScript with a
 * Tailwind subset" for the rationale.
 *
 * Status colors are deliberately muted — federal-feeling, not toy-like. The
 * UX rule (AGENTS.md) requires text + icon + color for every status; the
 * color is the third channel, not the only one.
 */
const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // USWDS-style "primary" — calm federal blue.
        primary: {
          lighter: "#dfe1e2",
          light: "#73b3e7",
          DEFAULT: "#005ea2",
          dark: "#1a4480",
          darker: "#162e51",
        },
        // Neutral grays based on USWDS gray scale.
        ink: {
          50: "#f9fafb",
          100: "#f0f0f0",
          200: "#dfe1e2",
          300: "#a9aeb1",
          400: "#71767a",
          500: "#565c65",
          600: "#3d4551",
          700: "#2d2e2f",
          800: "#1b1b1b",
        },
        // Status semantics — muted, accessible at AA against white.
        status: {
          // Match / Pass — muted green
          match: {
            bg: "#ecf3ec",
            border: "#538200",
            text: "#154c21",
            icon: "#446a00",
          },
          // Mismatch — muted red
          mismatch: {
            bg: "#f8eeee",
            border: "#b50909",
            text: "#7e2023",
            icon: "#9c1f1f",
          },
          // Missing — muted amber
          missing: {
            bg: "#fef0c8",
            border: "#a78327",
            text: "#5c4809",
            icon: "#7e6a14",
          },
          // Needs Review — muted blue
          review: {
            bg: "#e7f6f8",
            border: "#0076d6",
            text: "#0b4778",
            icon: "#005ea2",
          },
          // Uncertain — muted gray
          uncertain: {
            bg: "#f0f0f0",
            border: "#71767a",
            text: "#3d4551",
            icon: "#565c65",
          },
        },
      },
      fontFamily: {
        sans: [
          "'Source Sans 3'",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        serif: ["Merriweather", "Georgia", "serif"],
        mono: ["'Roboto Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      // 8px base unit — USWDS spacing units.
      spacing: {
        // 0.5 = 4px (half-unit), 1 = 8px, 2 = 16px, 3 = 24px, etc.
        // Tailwind's default scale is already 4px-based; we add semantic aliases.
        "u-half": "0.25rem", // 4px
        "u-1": "0.5rem", // 8px
        "u-2": "1rem", // 16px
        "u-3": "1.5rem", // 24px
        "u-4": "2rem", // 32px
        "u-5": "2.5rem", // 40px
        "u-6": "3rem", // 48px
        "u-8": "4rem", // 64px
      },
      // Minimum interactive target size — WCAG 2.2 AA.
      minWidth: {
        target: "44px",
      },
      minHeight: {
        target: "44px",
      },
      borderRadius: {
        sm: "2px",
        DEFAULT: "4px",
        md: "6px",
      },
      boxShadow: {
        focus: "0 0 0 3px rgba(0, 94, 162, 0.35)",
      },
    },
  },
  plugins: [],
};

export default config;
