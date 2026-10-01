import typography from "@tailwindcss/typography";

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
        sans:  ['"Inter Variable"', "Inter", "ui-sans-serif", "system-ui", "-apple-system", "sans-serif"],
        serif: ["Georgia", "Cambria", '"Times New Roman"', "Times", "serif"],
        // Titles and section headings on reading surfaces (IR-356), for an
        // academic, library feel. Everything else stays Inter.
        display: ['"EB Garamond"', "Georgia", "Cambria", "serif"],
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

      // Answer Markdown (IR-450). Used with `prose-sm`, whose 14px base is
      // the repo's `base` size; only colours and structure are set here.
      typography: ({ theme }) => ({
        DEFAULT: {
          css: {
            color: theme("colors.stone.700"),
            maxWidth: "none",
            "h1, h2, h3, h4": { color: theme("colors.stone.900"), fontWeight: "600" },
            strong: { color: theme("colors.stone.900") },
            "ul > li::marker, ol > li::marker": { color: theme("colors.stone.400") },
            blockquote: {
              fontStyle: "normal",
              fontWeight: "400",
              color: theme("colors.stone.600"),
              borderLeftColor: theme("colors.gold.DEFAULT"),
            },
            "blockquote p:first-of-type::before": { content: "none" },
            "blockquote p:last-of-type::after": { content: "none" },
            "code::before": { content: "none" },
            "code::after": { content: "none" },
            code: {
              color: theme("colors.brand.DEFAULT"),
              backgroundColor: theme("colors.gray.100"),
              borderRadius: "0.25rem",
              padding: "0.125rem 0.25rem",
              fontWeight: "500",
            },
            table: { width: "100%" },
            "thead th": {
              color: theme("colors.stone.900"),
              backgroundColor: theme("colors.stone.50"),
              fontWeight: "600",
            },
            "th, td": {
              border: `1px solid ${theme("colors.stone.200")}`,
              padding: "0.375rem 0.625rem",
            },
            "thead, tbody tr": { borderBottomWidth: "0" },
          },
        },
      }),

      keyframes: {
        "fade-in-up": {
          "0%":   { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          "0%":   { opacity: "0" },
          "100%": { opacity: "1" },
        },
        // A citation's highlight briefly reads brighter on arrival, so a
        // reader's eye finds it on the page rather than searching for a
        // static box among the surrounding text (IR-335).
        "citation-flash": {
          "0%":   { backgroundColor: "rgb(252 211 77 / 0.75)" },
          "100%": { backgroundColor: "rgb(252 211 77 / 0.35)" },
        },
      },
      animation: {
        "fade-in-up": "fade-in-up 0.3s ease-out",
        "fade-in":    "fade-in 0.2s ease-out",
        "citation-flash": "citation-flash 1.6s ease-out",
      },
    },
  },

  plugins: [
    // The `prose` classes on Ask IRIS answers and the AI Overview (IR-450).
    // Without it they emit no CSS and Preflight flattens every heading,
    // list and table. @tailwindcss/forms is still not needed.
    typography,
  ],
};
