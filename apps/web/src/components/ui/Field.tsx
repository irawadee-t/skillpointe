"use client";

import { Children, cloneElement, isValidElement, ReactElement, useId } from "react";

/**
 * Labeled form field wrapper with proper a11y binding.
 *
 * The input is a DIRECT child of a real <label htmlFor>, and error/hint text
 * is bound via aria-describedby. Errors get role="alert" so screen readers
 * announce them immediately.
 *
 *   <Field label="Email" hint="We won't share it." error={errors.email}>
 *     <input type="email" name="email" />
 *   </Field>
 */
export function Field({
  label,
  hint,
  error,
  required,
  children,
}: {
  label: string;
  hint?: string;
  error?: string | null;
  required?: boolean;
  children: React.ReactNode;
}) {
  const rid = useId();
  const inputId = `${rid}-input`;
  const hintId = hint ? `${rid}-hint` : undefined;
  const errorId = error ? `${rid}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  // Clone the input child and inject id + aria props. Only the first input-like
  // child gets the binding; siblings (buttons, hints) are left alone.
  let bound = false;
  const boundChildren = Children.map(children, (child) => {
    if (!isValidElement(child)) return child;
    if (bound) return child;
    const type = (child as ReactElement).type;
    const tagName = typeof type === "string" ? type : "";
    if (!["input", "textarea", "select"].includes(tagName)) return child;
    bound = true;
    const props = child.props as Record<string, unknown>;
    return cloneElement(child as ReactElement<Record<string, unknown>>, {
      id: (props.id as string) ?? inputId,
      "aria-describedby": describedBy,
      "aria-invalid": error ? true : undefined,
      "aria-required": required || undefined,
    });
  });

  return (
    <div>
      <label
        htmlFor={inputId}
        className="mb-2 block text-caption font-medium tracking-[0.01em] text-slate"
      >
        {label}
        {required && <span aria-hidden="true" className="ml-0.5 text-studio-maroon">*</span>}
      </label>
      {boundChildren}
      {hint && !error && (
        <span id={hintId} className="mt-1.5 block text-micro text-slate-muted">
          {hint}
        </span>
      )}
      {error && (
        <span
          id={errorId}
          role="alert"
          className="mt-1.5 block text-micro text-studio-maroon"
        >
          {error}
        </span>
      )}
    </div>
  );
}
