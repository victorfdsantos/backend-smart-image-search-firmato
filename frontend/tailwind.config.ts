import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        lato: ["Lato", "sans-serif"],
        serif: ["DM Serif Display", "serif"],
      },
      colors: {
        firmato: {
          bg: "#f8f8f8",
          surface: "#ffffff",
          text: "#2c2c2c",
          muted: "#6b6b6b",
          accent: "#a67c52",
          "accent-light": "#d4b08c",
          border: "#eaeaea",
          "border-dark": "#dddddd",
        },
      },
      keyframes: {
        fadeIn: {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        slideDown: {
          from: { opacity: "0", transform: "translateY(-8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        loadingBar: {
          "0%": { transform: "translateX(-100%)" },
          "50%": { transform: "translateX(0%)" },
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-in": "fadeIn 0.35s ease forwards",
        "slide-down": "slideDown 0.2s ease forwards",
        "loading-bar": "loadingBar 1.6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;