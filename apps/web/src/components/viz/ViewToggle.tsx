"use client";

/**
 * ViewToggle — contract-styled segmented control (sentence case, hairline
 * border, dark-cork active state matching the app-wide chip pattern).
 */

export interface ViewToggleOption<T extends string> {
  value: T;
  label: string;
}

interface Props<T extends string> {
  value: T;
  options: ViewToggleOption<T>[];
  onChange: (value: T) => void;
  ariaLabel?: string;
}

export function ViewToggle<T extends string>({ value, options, onChange, ariaLabel }: Props<T>) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className="inline-flex items-center gap-0.5 rounded-md border border-hairline bg-white p-0.5"
    >
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            onClick={() => onChange(opt.value)}
            aria-pressed={active}
            className={`rounded-[7px] px-3 py-1.5 text-caption transition-colors ${
              active
                ? "bg-ink font-medium text-white"
                : "text-slate hover:text-cohere-ink"
            }`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
