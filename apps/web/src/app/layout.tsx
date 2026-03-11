import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SkillPointe Match",
  description: "Bi-directional ranking, explanation, and planning platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
