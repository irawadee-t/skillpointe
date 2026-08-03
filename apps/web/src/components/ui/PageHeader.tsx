import { MonoLabel } from "./MonoLabel";
import { Reveal } from "./Reveal";
import { TourLaunchButton } from "@/components/tour/TourLaunchButton";

/** Standard dashboard page header: mono eyebrow + display title + lead + actions. */
export function PageHeader({
  eyebrow,
  title,
  lead,
  actions,
}: {
  eyebrow?: React.ReactNode;
  title: string;
  lead?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <Reveal className="flex flex-col gap-4 border-b border-hairline pb-8 sm:flex-row sm:items-end sm:justify-between">
      <div className="max-w-prose">
        {eyebrow && <MonoLabel className="mb-3 block text-studio-maroon">{eyebrow}</MonoLabel>}
        <h1 className="font-display text-card sm:text-heading text-cohere-ink">
          {title}
        </h1>
        {lead && <p className="mt-3 text-body-lg text-slate">{lead}</p>}
      </div>
      {/* The tour icon renders itself only on pages with a registered tour. */}
      <div className="flex flex-shrink-0 items-center gap-3">
        {actions}
        <TourLaunchButton />
      </div>
    </Reveal>
  );
}
