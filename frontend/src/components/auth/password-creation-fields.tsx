"use client";

import { useState, type ClipboardEvent } from "react";

export const passwordRequirements = [
  ["At least 8 characters", (value: string) => value.length >= 8],
  ["One uppercase letter", (value: string) => /[A-Z]/.test(value)],
  ["One lowercase letter", (value: string) => /[a-z]/.test(value)],
  ["One number", (value: string) => /\d/.test(value)],
  ["One special character", (value: string) => /[^A-Za-z0-9]/.test(value)],
] as const;

export function isStrongPassword(value: string) {
  return passwordRequirements.every(([, check]) => check(value));
}

type Props = {
  password: string;
  confirmPassword: string;
  onPasswordChange: (value: string) => void;
  onConfirmPasswordChange: (value: string) => void;
  passwordLabel?: string;
  confirmLabel?: string;
  passwordError?: string;
  confirmError?: string;
};

export function PasswordCreationFields({ password, confirmPassword, onPasswordChange, onConfirmPasswordChange, passwordLabel = "Password", confirmLabel = "Confirm password", passwordError, confirmError }: Props) {
  const [visible, setVisible] = useState({ password: false, confirm: false });
  const [manualWarning, setManualWarning] = useState(false);
  const blockConfirmationClipboard = (event: ClipboardEvent<HTMLInputElement>) => {
    event.preventDefault();
    setManualWarning(true);
  };
  const field = (kind: "password" | "confirm", label: string, value: string, onChange: (value: string) => void, error?: string) => (
    <label className="grid gap-2 font-semibold text-slate-800">
      {label}
      <span className="flex rounded-xl border border-slate-300 bg-white focus-within:ring-2 focus-within:ring-emerald-600">
        <input
          aria-invalid={Boolean(error)}
          type={visible[kind] ? "text" : "password"}
          autoComplete="new-password"
          value={value}
          onChange={(event) => { onChange(event.target.value); if (kind === "confirm") setManualWarning(false); }}
          onPaste={kind === "confirm" ? blockConfirmationClipboard : undefined}
          onCopy={kind === "confirm" ? blockConfirmationClipboard : undefined}
          onCut={kind === "confirm" ? blockConfirmationClipboard : undefined}
          className="min-h-12 min-w-0 flex-1 rounded-xl px-4 outline-none"
          required
        />
        <button type="button" onClick={() => setVisible((current) => ({ ...current, [kind]: !current[kind] }))} className="px-4 text-sm font-semibold text-emerald-800" aria-label={`${visible[kind] ? "Hide" : "Show"} ${kind === "confirm" ? "confirmation password" : "password"}`}>{visible[kind] ? "Hide" : "Show"}</button>
      </span>
      {error && <span role="alert" className="text-sm font-medium text-red-700">{error}</span>}
    </label>
  );
  return <div className="space-y-5">
    {field("password", passwordLabel, password, onPasswordChange, passwordError)}
    <div>
      {field("confirm", confirmLabel, confirmPassword, onConfirmPasswordChange, confirmError)}
      {manualWarning && <p role="alert" className="mt-2 text-sm font-medium text-red-700">Please type the password again manually to confirm.</p>}
    </div>
    <div className="rounded-xl bg-slate-50 p-3 text-sm" aria-live="polite">
      <p className="font-semibold text-slate-800">Password requirements:</p>
      <ul className="mt-2 space-y-1">{passwordRequirements.map(([label, check]) => <li key={label} className={check(password) ? "text-emerald-700" : "text-slate-600"}>{check(password) ? "✓" : "✕"} {label}</li>)}</ul>
      <p className="mt-2 text-slate-600">Avoid commonly used passwords and passwords that closely match your name, email, or mobile number.</p>
      {confirmPassword && <p className={`mt-2 font-semibold ${password === confirmPassword ? "text-emerald-700" : "text-red-700"}`}>{password === confirmPassword ? "✓ Passwords match" : "✕ Passwords do not match"}</p>}
    </div>
  </div>;
}
