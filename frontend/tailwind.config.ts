import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        night: "#0E0E0E",
        ink: "#151515",
        cinnabar: {
          DEFAULT: "#E8442A",
          dim: "#C83820",
          deep: "#8B4A3A",
          wash: "#1f0f0c",
        },
        jet: "#3D3D3D",
        bone: "#F7EDE2",
        mist: "#6B6B6B",
        sienna: "#8B4A3A",
        "sea-salt": "#F7EDE2",
        "gray-text": "#6B6B6B",
        surface: {
          DEFAULT: "#1A1A1A",
          input: "#2A2A2A",
          raised: "#1F1F1F",
        },
        hairline: "rgba(255,255,255,0.08)",
        "hairline-strong": "rgba(255,255,255,0.14)",
      },
      fontFamily: {
        display: ['"Playfair Display"', "ui-serif", "Georgia", "serif"],
        sans: ['"Geist"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        "mega": ["clamp(3.5rem, 10vw, 8.5rem)", { lineHeight: "0.92", letterSpacing: "-0.04em" }],
        "editorial": ["clamp(2.5rem, 6vw, 5rem)", { lineHeight: "0.98", letterSpacing: "-0.035em" }],
        "eyebrow": ["0.68rem", { lineHeight: "1", letterSpacing: "0.22em" }],
      },
      borderRadius: {
        squircle: "2rem",
        bezel: "calc(2rem - 0.375rem)",
      },
      boxShadow: {
        diffuse:
          "0 40px 80px -40px rgba(232,68,42,0.18), 0 20px 40px -20px rgba(0,0,0,0.5)",
        inset:
          "inset 0 1px 0 rgba(255,255,255,0.08), inset 0 -1px 0 rgba(0,0,0,0.4)",
        cinnabar: "0 20px 60px -30px rgba(232,68,42,0.5)",
      },
      backgroundImage: {
        grain:
          "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.55 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>\")",
        mesh:
          "radial-gradient(1200px 600px at 85% 10%, rgba(232,68,42,0.10), transparent 60%), radial-gradient(900px 500px at 10% 90%, rgba(139,74,58,0.10), transparent 60%), radial-gradient(600px 400px at 50% 50%, rgba(247,237,226,0.03), transparent 60%)",
      },
      transitionTimingFunction: {
        spring: "cubic-bezier(0.32, 0.72, 0, 1)",
        fluid: "cubic-bezier(0.16, 1, 0.3, 1)",
      },
      keyframes: {
        "float": {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-6px)" },
        },
        "shimmer": {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "pulse-dot": {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.5", transform: "scale(0.85)" },
        },
        "draw": {
          from: { strokeDashoffset: "1000" },
          to: { strokeDashoffset: "0" },
        },
        "slide-in-right": {
          from: { transform: "translateX(100%)" },
          to: { transform: "translateX(0)" },
        },
        "slide-out-right": {
          from: { transform: "translateX(0)" },
          to: { transform: "translateX(100%)" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "fade-out": {
          from: { opacity: "1" },
          to: { opacity: "0" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "translate(-50%, -48%) scale(0.96)" },
          to: { opacity: "1", transform: "translate(-50%, -50%) scale(1)" },
        },
        "scale-out": {
          from: { opacity: "1", transform: "translate(-50%, -50%) scale(1)" },
          to: { opacity: "0", transform: "translate(-50%, -48%) scale(0.97)" },
        },
      },
      animation: {
        float: "float 6s cubic-bezier(0.45, 0, 0.55, 1) infinite",
        shimmer: "shimmer 2.5s linear infinite",
        "pulse-dot": "pulse-dot 1.8s cubic-bezier(0.45, 0, 0.55, 1) infinite",
        draw: "draw 2.5s cubic-bezier(0.65, 0, 0.35, 1) forwards",
        "slide-in-right": "slide-in-right 220ms cubic-bezier(0.32, 0.72, 0, 1)",
        "slide-out-right": "slide-out-right 180ms cubic-bezier(0.4, 0, 1, 1)",
        "fade-in": "fade-in 180ms ease-out",
        "fade-out": "fade-out 150ms ease-in",
        "scale-in": "scale-in 220ms cubic-bezier(0.16, 1, 0.3, 1)",
        "scale-out": "scale-out 160ms cubic-bezier(0.4, 0, 1, 1)",
      },
    },
  },
  plugins: [],
} satisfies Config;
