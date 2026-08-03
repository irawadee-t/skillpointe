"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Menu, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { cn } from "@/lib/utils";

type NavItem = { label: string; href: string };

export function DashboardNav({
  navItems,
  email,
  homeHref,
}: {
  navItems: NavItem[];
  email: string;
  homeHref: string;
}) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  const isActive = (href: string) =>
    href === homeHref ? pathname === href : pathname.startsWith(href);

  return (
    <nav className="sticky top-0 z-50 border-b border-hairline bg-white/85 backdrop-blur-md">
      <div className="container-cohere">
        <div className="flex h-16 items-center justify-between">
          <div className="flex items-center gap-10">
            <Link href={homeHref} className="flex-shrink-0">
              <Image
                src="/spf-logo.png"
                alt="SKILLED Nation"
                width={124}
                height={34}
                className="brightness-0"
                priority
              />
            </Link>

            <div className="hidden items-center gap-1 md:flex">
              {navItems.map((item) => {
                const active = isActive(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "relative px-3 py-2 text-caption transition-colors duration-200",
                      active ? "text-cohere-ink" : "text-slate-muted hover:text-ink",
                    )}
                  >
                    {item.label}
                    {active && (
                      <motion.span
                        layoutId="nav-active"
                        className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-ink"
                        transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                      />
                    )}
                  </Link>
                );
              })}
            </div>
          </div>

          <div className="flex items-center gap-4">
            <span className="hidden text-micro text-slate-muted lg:inline">{email}</span>
            <Link
              href="/api/auth/signout"
              prefetch={false}
              className="hidden text-caption text-slate-muted transition-colors hover:text-ink md:inline"
            >
              Sign out
            </Link>
            <button
              onClick={() => setMenuOpen((v) => !v)}
              className="text-ink md:hidden"
              aria-label="Toggle menu"
            >
              {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile menu */}
      <AnimatePresence>
        {menuOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden border-t border-hairline md:hidden"
          >
            <div className="container-cohere flex flex-col gap-1 py-4">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMenuOpen(false)}
                  className={cn(
                    "rounded-sm px-3 py-2.5 text-body transition-colors",
                    isActive(item.href)
                      ? "bg-stone text-cohere-ink"
                      : "text-slate hover:bg-stone/50",
                  )}
                >
                  {item.label}
                </Link>
              ))}
              <div className="mt-2 flex items-center justify-between border-t border-hairline px-3 pt-4">
                <span className="text-micro text-slate-muted">{email}</span>
                <Link
                  href="/api/auth/signout"
                  prefetch={false}
                  className="text-caption text-slate-muted hover:text-ink"
                >
                  Sign out
                </Link>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  );
}
