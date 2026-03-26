import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        spf: {
          navy:       "#28486d",
          "navy-light": "#3a6399",
          "navy-dark": "#1c3350",
          orange:     "#f48a20",
          "orange-light": "#f9a84e",
          "orange-dark": "#d4740f",
          gray:       "#9d9b9c",
          "gray-light": "#c4c3c3",
        },
        ink: "#111111",
      },
    },
  },
  plugins: [],
};

export default config;
