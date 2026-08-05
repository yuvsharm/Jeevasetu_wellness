import type { InputHTMLAttributes } from "react";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  error?: string;
  hint?: string;
};

export function FormField({ label, error, hint, id, ...props }: Props) {
  const fieldId = id ?? props.name;
  const descriptionId = error ? `${fieldId}-error` : hint ? `${fieldId}-hint` : undefined;
  return (
    <div>
      <label htmlFor={fieldId} className="mb-2 block text-sm font-semibold text-slate-800">
        {label}
      </label>
      <input
        {...props}
        id={fieldId}
        aria-invalid={Boolean(error)}
        aria-describedby={descriptionId}
        className="min-h-12 w-full rounded-xl border border-slate-300 bg-white px-4 text-base text-slate-950 outline-none transition focus:border-emerald-700 focus:ring-3 focus:ring-emerald-100 aria-invalid:border-red-600"
      />
      {error ? (
        <p id={`${fieldId}-error`} className="mt-2 text-sm font-medium text-red-700" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p id={`${fieldId}-hint`} className="mt-2 text-sm text-slate-600">{hint}</p>
      ) : null}
    </div>
  );
}
