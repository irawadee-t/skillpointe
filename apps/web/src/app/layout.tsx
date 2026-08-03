import type { Metadata, Viewport } from "next";
import { EB_Garamond, Inter } from "next/font/google";
import "./globals.css";

import { MotionProvider } from "@/components/MotionProvider";

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
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000"
  ),
  title: {
    default: "SKILLED Nation Match",
    template: "%s · SKILLED Nation",
  },
  description:
    "Real jobs, ranked for you. The platform where SKILLED Scholars and skilled workers meet the employers who fund the training.",
  applicationName: "SKILLED Nation Match",
  openGraph: {
    title: "SKILLED Nation Match",
    description:
      "Real jobs, ranked for you. Where skilled workers meet the employers who fund the training.",
    siteName: "SKILLED Nation",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "SKILLED Nation Match",
    description: "Real jobs, ranked for you.",
  },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  themeColor: "#17140f",
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
      <body className="bg-canvas text-ink antialiased">
        <MotionProvider>{children}</MotionProvider>
      </body>
    </html>
  );
}
