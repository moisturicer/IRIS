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
        // Raised one step in IR-452; components carry the same sizes inline,
        // so the two move together or the app renders at two scales.
        "3xs": ["11px", { lineHeight: "15px" }],
        "2xs": ["12px", { lineHeight: "17px" }],
        xs:   ["13px", { lineHeight: "18px" }],
        sm:   ["14px", { lineHeight: "21px" }],
        base: ["15px", { lineHeight: "22px" }],
        md:   ["16px", { lineHeight: "24px" }],
        lg:   ["17px", { lineHeight: "26px" }],
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
      // Answer Markdown (IR-450/451/452). Used with `prose-base`, whose 16px
      // base is a reading size; the interface around it stays on its own scale.
      typography: ({ theme }) => {
        // Typography zeroes the outer padding of the first and last cell so a
        // prose table lines up with the text column. A bordered table needs it
        // back, or the first column sits flush against its own border. These
        // keys match the plugin's exactly so the values merge in place.
        const cells = {
          "thead th": {
            paddingTop: "0.4rem",
            paddingBottom: "0.4rem",
            paddingInlineStart: "0.7rem",
            paddingInlineEnd: "0.7rem",
          },
          "thead th:first-child": { paddingInlineStart: "0.7rem" },
          "thead th:last-child": { paddingInlineEnd: "0.7rem" },
          "tbody td, tfoot td": {
            paddingTop: "0.4rem",
            paddingBottom: "0.4rem",
            paddingInlineStart: "0.7rem",
            paddingInlineEnd: "0.7rem",
          },
          "tbody td:first-child, tfoot td:first-child": { paddingInlineStart: "0.7rem" },
          "tbody td:last-child, tfoot td:last-child": { paddingInlineEnd: "0.7rem" },
        };

        // Every gap roughly halved, and a heading's own space moved above it:
        // symmetric margins leave a heading floating between two sections
        // instead of sitting with the text it introduces (IR-452).
        const rhythm = {
          h1: { marginBottom: "0.25em" },
          h2: { marginTop: "1.2em", marginBottom: "0.25em" },
          h3: { marginTop: "1em", marginBottom: "0.2em" },
          h4: { marginTop: "1em", marginBottom: "0.2em" },
          "h1 + *, h2 + *, h3 + *, h4 + *": { marginTop: "0" },
          p: { marginTop: "0.7em", marginBottom: "0.7em" },
          "ul, ol": { marginTop: "0.7em", marginBottom: "0.7em" },
          "li": { marginTop: "0.2em", marginBottom: "0.2em" },
          blockquote: { marginTop: "0.9em", marginBottom: "0.9em" },
          pre: { marginTop: "0.9em", marginBottom: "0.9em" },
          hr: { marginTop: "1.2em", marginBottom: "1.2em" },
        };

        // `prose-base` restates sizes, cell padding and every one of these
        // margins after DEFAULT, so anything set here has to be repeated
        // there or the later rule wins on source order.
        const restated = {
          table: { width: "100%", fontSize: "0.95em", lineHeight: "1.6", marginTop: "1em", marginBottom: "1em" },
          ...rhythm,
          ...cells,
        };

        return {
          DEFAULT: {
            css: {
              color: theme("colors.stone.700"),
              maxWidth: "none",
              "h1, h2, h3, h4": {
                color: theme("colors.brand.DEFAULT"),
                // The same face the paper view gives a title (IR-356).
                fontFamily: theme("fontFamily.display").join(", "),
                // Only EB Garamond 600 is loaded; see main.tsx.
                fontWeight: "600",
              },
              // A rule under the top two levels is what makes a section start
              // read as one, rather than as a bold line in the prose.
              "h1, h2": {
                borderBottom: `1px solid ${theme("colors.stone.200")}`,
                paddingBottom: "0.25em",
              },
              // A model-written `---` under a heading repeats the rule the
              // heading already draws, and spends 3em of blank page doing it.
              "h1 + hr, h2 + hr": { display: "none" },
              // Whatever follows a rule starts against it, not a line later.
              "hr + *": { marginTop: "0" },
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
              // Typography ships tables at 0.875em, which is the least legible
              // thing in an answer; `restated` below raises it.
              "tbody tr:nth-child(even)": { backgroundColor: theme("colors.stone.50") },
              "thead th": { color: theme("colors.stone.900"), backgroundColor: theme("colors.stone.50"), fontWeight: "600" },
              "th, td": { border: `1px solid ${theme("colors.stone.200")}` },
              "thead, tbody tr": { borderBottomWidth: "0" },
              ...restated,
            },
          },
          base: { css: restated },
        };
      },

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
