import { cn } from "@/lib/utils";

/**
 * A grouped-content wrapper with a warm parchment background — used to give
 * a related cluster of cards its own visual room without resorting to tinted
 * washes. Sits inside `page-shell`, extends edge-to-edge inside it, and pads
 * its interior so children still align to the vertical rhythm.
 */
export function SectionBand({
  children,
  tone = "parchment",
  className,
}: {
  children: React.ReactNode;
  tone?: "parchment" | "stone" | "ink";
  className?: string;
}) {
  const surfaces = {
    parchment: "bg-parchment/70",
    stone: "bg-stone/60",
    ink: "bg-ink text-white",
  } as const;
  return (
    <section className={cn("-mx-6 rounded-2xl px-6 py-6 sm:-mx-8 sm:px-8 sm:py-8", surfaces[tone], className)}>
      {children}
    </section>
  );
}
