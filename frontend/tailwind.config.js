/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],

  theme: {
    extend: {
      colors: {
        // Primary brand color -- deep maroon
        gold: {
          DEFAULT: "#C59334",
          dark:    "#A87B2A",
          light:   "#D4A84A",
        },
        cream: "#F5F0E8",
        brand: {
          DEFAULT: "#6B0F12",
          light:   "#8B1316",
          dark:    "#4A0A0C",
          50:      "#fdf2f2",
          100:     "#fce4e4",
          200:     "#f9b8b9",
          300:     "#f48c8e",
          400:     "#ec5c5e",
          500:     "#e03133",
          600:     "#c01f21",
          700:     "#6B0F12",
          800:     "#4A0A0C",
          900:     "#2d0608",
        },
      },

      fontFamily: {
        sans:  ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "sans-serif"],
        serif: ["Georgia", "Cambria", '"Times New Roman"', "Times", "serif"],
      },

      fontSize: {
        // Keep consistent with the 13px base used across components
        "2xs": ["11px", { lineHeight: "16px" }],
        xs:   ["12px", { lineHeight: "16px" }],
        sm:   ["13px", { lineHeight: "20px" }],
        base: ["14px", { lineHeight: "20px" }],
        md:   ["15px", { lineHeight: "22px" }],
        lg:   ["16px", { lineHeight: "24px" }],
      },

      borderRadius: {
        DEFAULT: "0.5rem",
        lg:      "0.75rem",
        xl:      "1rem",
        "2xl":   "1.25rem",
      },

      boxShadow: {
        card: "0 1px 3px 0 rgb(0 0 0 / 0.06), 0 1px 2px -1px rgb(0 0 0 / 0.04)",
        "card-md": "0 4px 12px 0 rgb(0 0 0 / 0.08)",
      },

      // Line clamp utilities (built-in in Tailwind v3.3+, kept here for older versions)
      lineClamp: {
        1: "1",
        2: "2",
        3: "3",
      },
    },
  },

  plugins: [
    // TODO: add @tailwindcss/forms and @tailwindcss/typography if needed
  ],
};
