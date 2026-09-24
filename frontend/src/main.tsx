import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
// Self-hosted fonts (IR-356): bundled by Vite, so no request leaves for a
// font CDN. Inter was declared everywhere but never loaded until now, which
// left every screen in the operating system's fallback face.
import "@fontsource-variable/inter";
import "@fontsource/eb-garamond/latin-600.css";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
