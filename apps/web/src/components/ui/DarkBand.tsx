import { cn } from "@/lib/utils";

type BandTone = "green" | "navy" | "ink";

const TONE: Record<BandTone, string> = {
  green: "bg-cohere-green",
  navy: "bg-cohere-navy",
  ink: "bg-studio-dark-cork",
};

/** Full-width dark product/feature band. Text turns white inside. */
export function DarkBand({
  children,
  tone = "green",
  className,
}: {
  children: React.ReactNode;
  tone?: BandTone;
  className?: string;
}) {
  return (
    <section className={cn(TONE[tone], "text-white", className)}>
      <div className="container-cohere py-20 sm:py-28">{children}</div>
    </section>
  );
}
