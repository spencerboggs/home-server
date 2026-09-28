/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#14120e",
        panel: "#211e17",
        line: "#3c362b",
        paper: "#f4ecdc",
        muted: "#b5a890",
        brass: "#e2ac4a",
        moss: "#9db87a",
        clay: "#d26548",
      },
      fontFamily: {
        sans: ["Outfit", "Segoe UI", "sans-serif"],
        serif: ["Fraunces", "Palatino Linotype", "serif"],
      },
    },
  },
  plugins: [],
};
