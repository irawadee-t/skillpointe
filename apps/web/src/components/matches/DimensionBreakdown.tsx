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
      <p className="text-sm text-gray-500">No scoring breakdown available.</p>
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
  const scoreColor =
    dim.raw_score >= 80
      ? "bg-green-500"
      : dim.raw_score >= 60
        ? "bg-blue-500"
        : dim.raw_score >= 40
          ? "bg-amber-400"
          : "bg-red-400";

  const isNullHandled = dim.null_handling_applied;
  const barWidth = `${Math.round(dim.raw_score)}%`;

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-800">
            {formatDimensionName(dim.dimension)}
          </span>
          <span className="text-xs text-gray-400">
            (weight {dim.weight})
          </span>
          {isNullHandled && (
            <span
              className="text-xs text-amber-600 border border-amber-200 bg-amber-50 rounded px-1.5 py-0.5"
              title="Score is a neutral default — data missing for this dimension"
            >
              estimated
            </span>
          )}
        </div>
        <span
          className={`text-sm font-semibold ${
            dim.raw_score >= 70 ? "text-green-700" : "text-gray-700"
          }`}
        >
          {Math.round(dim.raw_score)}
        </span>
      </div>

      {/* Score bar */}
      <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${scoreColor} ${
            isNullHandled ? "opacity-50" : ""
          }`}
          style={{ width: barWidth }}
        />
      </div>

      {/* Rationale */}
      {dim.rationale && (
        <p className="text-xs text-gray-500 mt-1">{dim.rationale}</p>
      )}
    </div>
  );
}
