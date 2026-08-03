"use client";

import { useEffect } from "react";

// global-error replaces the ROOT layout when the layout itself throws, so it
// must render its own <html>/<body>. Kept dependency-free and inline-styled for
// exactly that reason (globals.css may not have loaded).
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          background: "#f7f4ee",
          color: "#17140f",
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
          textAlign: "center",
          padding: "0 24px",
        }}
      >
        <p
          style={{
            fontSize: 12,
            letterSpacing: "0.16em",
            textTransform: "uppercase",
            color: "#9d2235",
            fontWeight: 600,
            margin: 0,
          }}
        >
          Something went wrong
        </p>
        <h1 style={{ fontSize: 34, fontWeight: 600, margin: "18px 0 12px" }}>
          The app hit a snag.
        </h1>
        <p style={{ maxWidth: 420, color: "#4a4136", margin: 0, lineHeight: 1.6 }}>
          Something on our end failed to load. Reloading usually fixes it.
        </p>
        <button
          onClick={() => reset()}
          style={{
            marginTop: 28,
            padding: "10px 22px",
            background: "#17140f",
            color: "#fff",
            border: "none",
            borderRadius: 4,
            fontSize: 15,
            cursor: "pointer",
          }}
        >
          Reload
        </button>
      </body>
    </html>
  );
}
