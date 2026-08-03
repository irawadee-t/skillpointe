/**
 * DimensionBreakdown — visual breakdown of the 9 structured scoring dimensions.
 *
 * Used in the match detail view.
 * Shows each dimension's weight, raw score, and a proportional bar.
 * Null-handled dimensions are visually distinguished.
 */
import type { DimensionScoreItem } from "@/lib/api/applicant";
import { formatDimensionName, stripZeroDistance } from "@/lib/api/applicant";

interface DimensionBreakdownProps {
  dimensions: DimensionScoreItem[];
  /**
   * Engine weights are internals — hidden by default. The match detail page
   * surfaces them only inside its "How the math works" disclosure.
   */
  showWeights?: boolean;
}

export function DimensionBreakdown({ dimensions, showWeights = false }: DimensionBreakdownProps) {
  if (dimensions.length === 0) {
    return (
      <p className="text-caption text-slate-muted">No scoring breakdown available.</p>
    );
  }

  return (
    <div className="space-y-3">
      {dimensions.map((dim) => (
        <DimensionRow key={dim.dimension} dim={dim} showWeights={showWeights} />
      ))}
    </div>
  );
}

function DimensionRow({ dim, showWeights }: { dim: DimensionScoreItem; showWeights: boolean }) {
  const isNullHandled = dim.null_handling_applied;
  const barWidth = `${Math.round(dim.raw_score)}%`;

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className="text-caption font-medium text-ink">
            {formatDimensionName(dim.dimension)}
          </span>
          {showWeights && (
            <span className="text-micro text-slate-muted">
              (weight {dim.weight})
            </span>
          )}
          {isNullHandled && (
            <span
              className="text-micro text-slate-muted border border-hairline bg-stone rounded-sm px-1.5 py-0.5"
              title="Score is a neutral default. Data is missing for this dimension."
            >
              estimated
            </span>
          )}
        </div>
        <span className="text-caption font-semibold text-cohere-blue">
          {Math.round(dim.raw_score)}
        </span>
      </div>

      {/* Score bar */}
      <div className="h-2 bg-stone rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full bg-cohere-blue ${
            isNullHandled ? "opacity-30" : ""
          }`}
          style={{ width: barWidth }}
        />
      </div>

      {/* Rationale — sub-mile distances suppressed (CommuteChip's rule) */}
      {dim.rationale && (
        <p className="text-micro text-slate-muted mt-1">{stripZeroDistance(dim.rationale)}</p>
      )}
    </div>
  );
}
