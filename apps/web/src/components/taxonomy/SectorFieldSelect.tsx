"use client";

/**
 * SectorFieldSelect — the one control for picking a SKILLED Nation sector and
 * career field. Used by applicant onboarding, profile edit, and employer job
 * forms so the cascading rules live in exactly one place:
 *
 *   - sector first; the field list is constrained to that sector
 *   - multi-sector fields appear under each of their sectors
 *   - the sector's "Other X-related field" option is pinned last
 *   - changing sector clears a field that no longer belongs
 *
 * Validation is layered: this component makes invalid pairs unpickable, the
 * API returns 422 on a mismatched pair, and a DB trigger backstops both.
 */
import { Check } from "lucide-react";

import { SECTORS, fieldsForSector, CAREER_FIELDS } from "@/lib/taxonomy.generated";

export interface SectorFieldValue {
  sectorCode: string;
  fieldCode: string;
  sectorName: string;
  fieldName: string;
  isOther: boolean;
}

export function sectorFieldFromCodes(
  sectorCode?: string | null,
  fieldCode?: string | null,
): Partial<SectorFieldValue> {
  const field = CAREER_FIELDS.find((f) => f.code === fieldCode);
  // A stored sector wins; otherwise a single-sector field implies its sector.
  const sector =
    SECTORS.find((s) => s.code === sectorCode) ??
    (field && field.sectors.length === 1
      ? SECTORS.find((s) => s.code === field.sectors[0])
      : undefined);
  return {
    sectorCode: sector?.code ?? "",
    fieldCode: field && sector && field.sectors.includes(sector.code) ? field.code : field?.code ?? "",
    sectorName: sector?.name ?? "",
    fieldName: field?.name ?? "",
    isOther: field?.isOther ?? false,
  };
}

export function SectorFieldSelect({
  sectorCode,
  fieldCode,
  onChange,
  layout = "selects",
  sectorLabel = "Sector",
  fieldLabel = "Career field",
  required = false,
  className = "",
}: {
  sectorCode: string;
  fieldCode: string;
  onChange: (value: { sectorCode: string; fieldCode: string; sectorName: string; fieldName: string; isOther: boolean }) => void;
  /** "cards" = onboarding sector grid; "selects" = two dropdowns. */
  layout?: "cards" | "selects";
  sectorLabel?: string;
  fieldLabel?: string;
  required?: boolean;
  className?: string;
}) {
  const fields = sectorCode ? fieldsForSector(sectorCode) : [];

  const emit = (nextSector: string, nextField: string) => {
    const s = SECTORS.find((x) => x.code === nextSector);
    const f = CAREER_FIELDS.find((x) => x.code === nextField);
    onChange({
      sectorCode: nextSector,
      fieldCode: nextField,
      sectorName: s?.name ?? "",
      fieldName: f?.name ?? "",
      isOther: f?.isOther ?? false,
    });
  };

  const pickSector = (code: string) => {
    // Keep the field only if it also belongs to the new sector.
    const keeps = fieldCode && CAREER_FIELDS.some((f) => f.code === fieldCode && f.sectors.includes(code));
    emit(code, keeps ? fieldCode : "");
  };

  return (
    <div className={className}>
      {layout === "cards" ? (
        <div role="group" aria-label={sectorLabel} className="grid grid-cols-2 gap-3">
          {SECTORS.map((s) => {
            const selected = sectorCode === s.code;
            return (
              <button
                key={s.code}
                type="button"
                onClick={() => pickSector(s.code)}
                title={s.description}
                className={`rounded-xl border p-4 text-left transition-colors duration-150 ease-cohere ${
                  selected
                    ? "border-cohere-green bg-wash-green shadow-[0_1px_2px_rgba(12,10,9,0.04)]"
                    : "border-hairline bg-white hover:border-cohere-ink"
                }`}
              >
                <span className={`text-body font-medium ${selected ? "text-cohere-green" : "text-cohere-ink"}`}>
                  {s.name}
                </span>
                {selected && <Check className="float-right h-4 w-4 text-cohere-green" />}
              </button>
            );
          })}
        </div>
      ) : (
        <div className="mb-4">
          <label className="mb-1.5 block text-caption font-medium text-slate">{sectorLabel}</label>
          <select
            value={sectorCode}
            required={required}
            onChange={(e) => pickSector(e.target.value)}
            className="input-cohere"
          >
            <option value="">Select…</option>
            {SECTORS.map((s) => (
              <option key={s.code} value={s.code}>{s.name}</option>
            ))}
          </select>
        </div>
      )}

      {sectorCode && (
        <div className={layout === "cards" ? "mt-4 border-t border-hairline pt-4" : ""}>
          <label className="mb-1.5 block text-caption font-medium text-slate">{fieldLabel}</label>
          <select
            value={fieldCode}
            required={required}
            onChange={(e) => emit(sectorCode, e.target.value)}
            className="input-cohere"
          >
            <option value="">Select…</option>
            {fields.map((f) => (
              <option key={f.code} value={f.code}>{f.name}</option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}
