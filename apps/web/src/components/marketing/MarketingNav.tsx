"use client";

import Link from "next/link";
import { SkilledNationLogo } from "@/components/ui/Logo";
import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { cn } from "@/lib/utils";

const LINKS = [
  { label: "Applicants", href: "/login" },
  { label: "Employers", href: "/login" },
  { label: "How it works", href: "#how" },
];

export function MarketingNav() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    // Threshold matches the hero fade — once we're clearly off the hero video,
    // switch to the solid light nav so text stays legible.
    const onScroll = () => setScrolled(window.scrollY > 40);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Text color inverts with the background:
  //   scrolled=false → nav overlays the dark hero video → cream text
  //   scrolled=true  → nav is a solid light bar → ink text
  const linkColor = scrolled
    ? "text-ink hover:text-studio-maroon"
    : "text-studio-cream hover:text-studio-cream";

  return (
    <motion.nav
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        // Fixed so it can overlay the hero video without pushing content down;
        // the hero pads its own top-padding to leave room for this bar.
        "fixed inset-x-0 top-0 z-50 transition-all duration-300",
        scrolled
          ? "border-b border-hairline bg-white/90 backdrop-blur-md"
          : "bg-transparent",
      )}
    >
      <div className="container-cohere flex h-16 items-center justify-between">
        <Link href="/" className="flex-shrink-0">
          {/* Invert the logo on the dark hero so it reads as a cream mark;
              revert to the maroon-box light mark once we've scrolled off. */}
          <SkilledNationLogo width={150} invert={!scrolled} />
        </Link>

        <div className="hidden items-center gap-8 md:flex">
          {LINKS.map((l) => (
            <Link
              key={l.label}
              href={l.href}
              className={cn("group relative text-caption transition-colors", linkColor)}
            >
              {l.label}
              <span
                className={cn(
                  "absolute -bottom-1 left-0 h-px w-full origin-left scale-x-0 transition-transform duration-300 group-hover:scale-x-100",
                  scrolled ? "bg-studio-maroon" : "bg-studio-cream",
                )}
              />
            </Link>
          ))}
        </div>

        <div className="flex items-center gap-5">
          <Link
            href="/login"
            className={cn("text-caption transition-colors", linkColor)}
          >
            Sign in
          </Link>
          <Link
            href="/signup"
            className={cn(
              "inline-flex items-center rounded-md px-4 py-2 text-caption font-medium transition-colors",
              scrolled
                ? "bg-studio-dark-cork text-studio-cream hover:bg-studio-maroon"
                : "border border-studio-cream/40 bg-studio-cream/10 text-studio-cream backdrop-blur-sm hover:border-studio-cream hover:bg-studio-cream hover:text-studio-black",
            )}
          >
            Create account
          </Link>
        </div>
      </div>
    </motion.nav>
  );
}
