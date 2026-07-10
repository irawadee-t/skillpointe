import type { Metadata } from "next";
import { EB_Garamond, Inter } from "next/font/google";
import "./globals.css";

// ElevenLabs editorial display serif (Waldenburg Light substitute). Light weights
// only — the editorial signature is never bold.
const display = EB_Garamond({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-display",
  display: "swap",
});

// One text voice for the whole product. The former JetBrains Mono "system
// label" font is retired — labels, keys, and table headers all set in the
// body sans; numerals get font-variant-numeric where alignment matters.
const body = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-body",
  display: "swap",
});

export const metadata: Metadata = {
  title: "SKILLED Nation Match",
  description:
    "Real jobs, ranked for you. The platform where SKILLED Scholars and skilled workers meet the employers who fund the training.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${display.variable} ${body.variable}`}
    >
      <head>
        {/* No-JS fallback — never leave reveal-animated content hidden */}
        <noscript>
          <style>{`.reveal,.stagger>*{opacity:1!important;transform:none!important}`}</style>
        </noscript>
      </head>
      <body className="bg-canvas text-ink antialiased">{children}</body>
    </html>
  );
}
