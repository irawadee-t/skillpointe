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

const inputClass = "input-cohere";

export interface JobFormDefaults {
  title_raw?: string;
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
}

export function JobFormFields({
  defaults,
  onValidChange,
}: {
  defaults?: JobFormDefaults;
  onValidChange?: (valid: boolean) => void;
}) {
  const [title, setTitle] = useState<string>(defaults?.title_raw ?? "");
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
    </>
  );
}

function Field({
  label,
  required,
  error,
  children,
}: {
  label: string;
  required?: boolean;
  error?: string | null;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="mb-2 block text-caption font-medium tracking-[0.01em] text-slate">
        {label}
        {required && <span className="text-error-red ml-0.5">*</span>}
      </label>
      {children}
      {error && (
        <p className="mt-1 text-micro text-error-red" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
