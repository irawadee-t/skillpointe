/**
 * Shared job form fields — used by the new + edit job pages.
 *
 * Client component so we can wire inline validation:
 *   - Title: min 5 chars
 *   - Pay range: max >= min
 *
 * Consumers can pass `onValidChange` to gate the Save button.
 */
"use client";

import { useEffect, useState } from "react";
import { Field } from "@/components/ui";
import { SectorFieldSelect, sectorFieldFromCodes } from "@/components/taxonomy/SectorFieldSelect";

const inputClass = "input-cohere";

export interface JobFormDefaults {
  title_raw?: string;
  sector_code?: string;
  field_code?: string;
  city?: string;
  state?: string;
  work_setting?: string;
  travel_requirement?: string;
  pay_min?: number;
  pay_max?: number;
  pay_type?: string;
  description_raw?: string;
  requirements_raw?: string;
  experience_level?: string;
  is_active?: boolean;
  /** Per-job flag; null/undefined = inherit the company default. */
  accepts_internal_applications?: boolean | null;
  /** Effective value (per-job override folded with the company default). */
  internal_apply_effective?: boolean;
  required_profile_fields?: string[];
}

/** Profile-sourced groups an employer can require at apply time. */
const PROFILE_FIELD_OPTIONS: { key: string; label: string; hint: string }[] = [
  { key: "contact",      label: "Contact info",        hint: "Phone or email" },
  { key: "location",     label: "Location",            hint: "City and state" },
  { key: "program",      label: "Program or trade",    hint: "What they're trained in" },
  { key: "availability", label: "Availability",        hint: "Start date or program end" },
  { key: "credentials",  label: "Credentials",         hint: "At least one on their profile" },
  { key: "resume",       label: "Resume",              hint: "A file on their profile" },
];

export function JobFormFields({
  defaults,
  onValidChange,
}: {
  defaults?: JobFormDefaults;
  onValidChange?: (valid: boolean) => void;
}) {
  const [title, setTitle] = useState<string>(defaults?.title_raw ?? "");
  const seededTaxonomy = sectorFieldFromCodes(defaults?.sector_code, defaults?.field_code);
  const [sectorCode, setSectorCode] = useState<string>(seededTaxonomy.sectorCode ?? "");
  const [fieldCode, setFieldCode] = useState<string>(seededTaxonomy.fieldCode ?? "");
  // Internal-apply config. New jobs default to accepting applications on the
  // platform; edit pre-fills the stored/effective value.
  const [acceptsInternal, setAcceptsInternal] = useState<boolean>(
    defaults?.accepts_internal_applications ?? defaults?.internal_apply_effective ?? true,
  );
  const [requiredFields, setRequiredFields] = useState<string[]>(
    defaults?.required_profile_fields ?? ["contact", "location", "program"],
  );
  const [payMin, setPayMin] = useState<string>(
    defaults?.pay_min != null ? String(defaults.pay_min) : "",
  );
  const [payMax, setPayMax] = useState<string>(
    defaults?.pay_max != null ? String(defaults.pay_max) : "",
  );

  const titleTouched = title.length > 0;
  const titleError = titleTouched && title.trim().length < 5
    ? "Title needs to be at least 5 characters"
    : null;

  const payMinNum = payMin === "" ? null : Number(payMin);
  const payMaxNum = payMax === "" ? null : Number(payMax);
  const payError =
    payMinNum != null && payMaxNum != null && payMaxNum < payMinNum
      ? "Max pay can't be less than min pay"
      : null;

  const isValid = title.trim().length >= 5 && !payError;

  useEffect(() => {
    onValidChange?.(isValid);
  }, [isValid, onValidChange]);

  return (
    <>
      <Field label="Job title" required error={titleError}>
        <input
          type="text"
          name="title_raw"
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className={inputClass}
          placeholder="e.g. Welder – Entry Level"
          aria-invalid={titleError ? "true" : "false"}
        />
      </Field>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="City">
          <input type="text" name="city" defaultValue={defaults?.city} className={inputClass} placeholder="e.g. Austin" />
        </Field>
        <Field label="State">
          <input type="text" name="state" maxLength={2} defaultValue={defaults?.state} className={inputClass} placeholder="e.g. TX" />
        </Field>
      </div>

      <Field label="Sector and career field" hint="Drives matching and applicant filters. Pick the field that best describes the work.">
        <SectorFieldSelect
          sectorCode={sectorCode}
          fieldCode={fieldCode}
          onChange={(v) => { setSectorCode(v.sectorCode); setFieldCode(v.fieldCode); }}
        />
        <input type="hidden" name="sector_code" value={sectorCode} />
        <input type="hidden" name="field_code" value={fieldCode} />
      </Field>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="Work setting">
          <select name="work_setting" defaultValue={defaults?.work_setting ?? ""} className={inputClass}>
            <option value="">Not specified</option>
            <option value="on_site">On-site</option>
            <option value="hybrid">Hybrid</option>
            <option value="remote">Remote</option>
            <option value="flexible">Flexible</option>
          </select>
        </Field>
        <Field label="Travel requirement">
          <select name="travel_requirement" defaultValue={defaults?.travel_requirement ?? ""} className={inputClass}>
            <option value="">Not specified</option>
            <option value="none">None</option>
            <option value="light">Light</option>
            <option value="moderate">Moderate</option>
            <option value="frequent">Frequent</option>
          </select>
        </Field>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <Field label="Pay min">
          <input
            type="number"
            name="pay_min"
            min="0"
            step="0.01"
            value={payMin}
            onChange={(e) => setPayMin(e.target.value)}
            className={inputClass}
            placeholder="0"
            aria-invalid={payError ? "true" : "false"}
          />
        </Field>
        <Field label="Pay max" error={payError}>
          <input
            type="number"
            name="pay_max"
            min="0"
            step="0.01"
            value={payMax}
            onChange={(e) => setPayMax(e.target.value)}
            className={inputClass}
            placeholder="0"
            aria-invalid={payError ? "true" : "false"}
          />
        </Field>
        <Field label="Pay type">
          <select name="pay_type" defaultValue={defaults?.pay_type ?? ""} className={inputClass}>
            <option value="">Not specified</option>
            <option value="hourly">Hourly</option>
            <option value="annual">Annual</option>
            <option value="contract">Contract</option>
          </select>
        </Field>
      </div>

      <Field label="Experience level">
        <select name="experience_level" defaultValue={defaults?.experience_level ?? ""} className={inputClass}>
          <option value="">Not specified</option>
          <option value="entry">Entry level</option>
          <option value="mid">Mid level</option>
          <option value="senior">Senior</option>
          <option value="management">Management / supervisory</option>
        </select>
      </Field>

      <Field label="Job description">
        <textarea
          name="description_raw"
          rows={4}
          defaultValue={defaults?.description_raw}
          className={inputClass}
          placeholder="Describe the role, responsibilities, and work environment..."
        />
      </Field>

      <Field label="Requirements">
        <textarea
          name="requirements_raw"
          rows={3}
          defaultValue={defaults?.requirements_raw}
          className={inputClass}
          placeholder="List required qualifications, certifications, or experience..."
        />
      </Field>

      {/* Applications — internal apply configuration */}
      <div className="border-t border-hairline pt-5">
        <input type="hidden" name="accepts_internal_applications" value={acceptsInternal ? "true" : "false"} />
        <label className="flex cursor-pointer items-start gap-3">
          <input
            type="checkbox"
            checked={acceptsInternal}
            onChange={(e) => setAcceptsInternal(e.target.checked)}
            className="mt-1 accent-studio-maroon"
          />
          <span>
            <span className="block text-body font-medium text-cohere-ink">
              Accept applications on SKILLED Nation
            </span>
            <span className="mt-0.5 block text-caption text-slate">
              Applicants apply with their profile in two clicks. You pick what you need
              from them. Anything missing, they complete right in the apply form.
            </span>
          </span>
        </label>

        {acceptsInternal && (
          <div className="mt-4 rounded-[10px] border border-hairline bg-white">
            <p className="px-4 pt-3 text-caption text-slate">
              What do you need from applicants? These come from their profile automatically.
            </p>
            <div className="mt-2">
              {PROFILE_FIELD_OPTIONS.map((opt, i) => (
                <label
                  key={opt.key}
                  className={`flex cursor-pointer items-center justify-between gap-3 px-4 py-2.5 ${i > 0 ? "border-t border-hairline" : ""}`}
                >
                  <span className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      name="required_profile_fields"
                      value={opt.key}
                      checked={requiredFields.includes(opt.key)}
                      onChange={(e) =>
                        setRequiredFields((prev) =>
                          e.target.checked ? [...prev, opt.key] : prev.filter((k) => k !== opt.key),
                        )
                      }
                      className="accent-studio-maroon"
                    />
                    <span className="text-body text-cohere-ink">{opt.label}</span>
                  </span>
                  <span className="text-caption text-slate-muted">{opt.hint}</span>
                </label>
              ))}
            </div>
            <p className="border-t border-hairline px-4 py-3 text-caption text-slate-muted">
              Need anything beyond the profile? Add extra questions in the
              &ldquo;Screening questions&rdquo; section after saving.
            </p>
          </div>
        )}
      </div>
    </>
  );
}
