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
      <p className="text-sm text-zinc-500">No scoring breakdown available.</p>
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
          <span className="text-sm font-medium text-zinc-200">
            {formatDimensionName(dim.dimension)}
          </span>
          <span className="text-xs text-zinc-500">
            (weight {dim.weight})
          </span>
          {isNullHandled && (
            <span
              className="text-xs text-zinc-500 border border-zinc-700 bg-zinc-800 rounded px-1.5 py-0.5"
              title="Score is a neutral default — data missing for this dimension"
            >
              estimated
            </span>
          )}
        </div>
        <span className="text-sm font-semibold text-cyan-400">
          {Math.round(dim.raw_score)}
        </span>
      </div>

      {/* Score bar */}
      <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 bg-gradient-to-r from-cyan-500 to-blue-600 ${
            isNullHandled ? "opacity-30" : ""
          }`}
          style={{ width: barWidth }}
        />
      </div>

      {/* Rationale */}
      {dim.rationale && (
        <p className="text-xs text-zinc-500 mt-1">{dim.rationale}</p>
      )}
    </div>
  );
}
