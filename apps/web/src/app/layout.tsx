import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

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
      <body className={`${inter.className} font-sans antialiased bg-zinc-950 text-white`}>{children}</body>
    </html>
  );
}
