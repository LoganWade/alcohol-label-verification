import type { InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";
import { useId } from "react";

interface BaseProps {
  label: string;
  hint?: string;
  error?: string;
  optional?: boolean;
  children: (ids: { inputId: string; describedBy?: string }) => ReactNode;
}

/**
 * Form field wrapper that handles <label> association via useId so screen
 * readers always announce the field name. Hints are wired with aria-describedby.
 */
export function Field({
  label,
  hint,
  error,
  optional,
  children,
}: BaseProps) {
  const inputId = useId();
  const hintId = useId();
  const errorId = useId();
  const describedBy = [hint ? hintId : null, error ? errorId : null]
    .filter(Boolean)
    .join(" ") || undefined;

  return (
    <div className="space-y-1">
      <label htmlFor={inputId} className="label-base">
        {label}
        {optional && <span className="text-ink-400 font-normal"> (optional)</span>}
      </label>
      {hint && (
        <p id={hintId} className="text-xs text-ink-500">
          {hint}
        </p>
      )}
      {children({ inputId, describedBy })}
      {error && (
        <p id={errorId} role="alert" className="text-xs text-status-mismatch-text">
          {error}
        </p>
      )}
    </div>
  );
}

interface TextProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  label: string;
  hint?: string;
  error?: string;
  optional?: boolean;
}

export function TextField({ label, hint, error, optional, ...rest }: TextProps) {
  return (
    <Field label={label} hint={hint} error={error} optional={optional}>
      {({ inputId, describedBy }) => (
        <input
          id={inputId}
          aria-describedby={describedBy}
          aria-invalid={error ? "true" : undefined}
          className="input-base"
          {...rest}
        />
      )}
    </Field>
  );
}

interface AreaProps
  extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "id"> {
  label: string;
  hint?: string;
  error?: string;
  optional?: boolean;
}

export function TextArea({ label, hint, error, optional, ...rest }: AreaProps) {
  return (
    <Field label={label} hint={hint} error={error} optional={optional}>
      {({ inputId, describedBy }) => (
        <textarea
          id={inputId}
          aria-describedby={describedBy}
          aria-invalid={error ? "true" : undefined}
          className="input-base min-h-[6rem] font-mono text-sm"
          {...rest}
        />
      )}
    </Field>
  );
}
