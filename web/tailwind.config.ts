import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#12202B", paper: "#F3F6F6", line: "#D3DBDE", mute: "#5A6B76",
        brand: { DEFAULT: "#0F5C6E", dark: "#0B4655", soft: "#E1EEF1" },
        ok: { DEFAULT: "#17794F", soft: "#DDF1E6" }, warn: { DEFAULT: "#8A5A00", soft: "#FBEBCB" }, bad: { DEFAULT: "#B3261E", soft: "#FBE3E1" },
      },
      fontFamily: { sans: ["'Schibsted Grotesk'", "system-ui", "sans-serif"], mono: ["'JetBrains Mono'", "ui-monospace", "monospace"] },
      borderRadius: { DEFAULT: "6px" },
    },
  },
  plugins: [],
} satisfies Config;
