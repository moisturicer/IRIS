import { lazy } from "react";

// Lazy: pdf.js is a large dependency (its worker alone is over a megabyte),
// and most visits to a paper never open its reader. Splitting it out of the
// main bundle means only a reader who actually opens it pays for it. One
// wrapper, shared by the manuscript and a supporting document (IR-1203).
export const PaperPdfReader = lazy(() =>
  import("./PaperPdfReader").then((m) => ({ default: m.PaperPdfReader })),
);
