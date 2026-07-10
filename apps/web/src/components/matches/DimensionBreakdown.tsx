/**
 * DimensionBreakdown — visual breakdown of the 9 structured scoring dimensions.
 *
 * Used in the match detail view.
 * Shows each dimension's weight, raw score, and a proportional bar.
 * Null-handled dimensions are visually distinguished.
 */
import type { DimensionScoreItem } from "@/lib/api/applicant";
import { formatDimensionName } from "@/lib/api/applicant";

interface DimensionBreakdownProps {
  dimensions: DimensionScoreItem[];
}

export function DimensionBreakdown({ dimensions }: DimensionBreakdownProps) {
  if (dimensions.length === 0) {
    return (
      <p className="text-caption text-slate-muted">No scoring breakdown available.</p>
    );
  }

  return (
    <div className="space-y-3">
      {dimensions.map((dim) => (
        <DimensionRow key={dim.dimension} dim={dim} />
      ))}
    </div>
  );
}

function DimensionRow({ dim }: { dim: DimensionScoreItem }) {
  const isNullHandled = dim.null_handling_applied;
  const barWidth = `${Math.round(dim.raw_score)}%`;

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className="text-caption font-medium text-ink">
            {formatDimensionName(dim.dimension)}
          </span>
          <span className="text-micro text-slate-muted">
            (weight {dim.weight})
          </span>
          {isNullHandled && (
            <span
              className="text-micro text-slate-muted border border-hairline bg-stone rounded-sm px-1.5 py-0.5"
              title="Score is a neutral default — data missing for this dimension"
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
          className={`h-full rounded-full transition-all duration-700 bg-cohere-blue ${
            isNullHandled ? "opacity-30" : ""
          }`}
          style={{ width: barWidth }}
        />
      </div>

      {/* Rationale */}
      {dim.rationale && (
        <p className="text-micro text-slate-muted mt-1">{dim.rationale}</p>
      )}
    </div>
  );
}
