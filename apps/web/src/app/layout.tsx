import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SkillPointe Match",
  description: "Bi-directional ranking, explanation, and planning platform for skilled trades careers",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="font-sans antialiased bg-white text-zinc-900">{children}</body>
    </html>
  );
}
