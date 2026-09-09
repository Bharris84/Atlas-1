import type { Config } from "tailwindcss";

/**
 * A restrained palette on purpose. Atlas is an analyst's tool: green and red
 * mean "this number passed or failed a stated test", never "get excited".
 */
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          50: "#f6f7f9",
          100: "#eceef2",
          200: "#d4d9e2",
          300: "#aeb7c7",
          400: "#8290a7",
          500: "#61708b",
          600: "#4c5872",
          700: "#3e485c",
          800: "#353d4e",
          900: "#1f2430",
          950: "#141821",
        },
        pass: {
          50: "#f0f9f2",
          100: "#dcf0e1",
          500: "#2f9e5f",
          600: "#25804d",
          700: "#1f6640",
        },
        caution: {
          50: "#fdf7ec",
          100: "#faecd2",
          500: "#c98a1e",
          600: "#a76f16",
          700: "#875913",
        },
        fail: {
          50: "#fdf2f2",
          100: "#fbe0e0",
          500: "#c0433f",
          600: "#a03530",
          700: "#822c28",
        },
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
