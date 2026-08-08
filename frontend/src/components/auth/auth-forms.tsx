"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm, type FieldValues, type Path, type UseFormSetError } from "react-hook-form";
import type { ZodType } from "zod";

import { StatusPanel } from "@/components/feedback/status-panel";
import { FormField } from "@/components/forms/form-field";
import { ClientApiError, requestJson } from "@/lib/api/client";
import { sessionEndpoints } from "@/lib/api/endpoints";
import {
  forgotPasswordSchema,
  loginSchema,
  registrationSchema,
  resetPasswordSchema,
  type ForgotPasswordInput,
  type LoginInput,
  type RegistrationInput,
  type ResetPasswordInput,
} from "@/lib/forms/schemas";

function validate<T extends FieldValues>(
  schema: ZodType<T>,
  values: T,
  setError: UseFormSetError<T>,
) {
  const result = schema.safeParse(values);
  if (result.success) return result.data;
  for (const issue of result.error.issues) {
    const field = issue.path[0];
    if (typeof field === "string") setError(field as Path<T>, { message: issue.message });
  }
  return null;
}

function applyApiError<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  setMessage: (message: string) => void,
) {
  if (error instanceof ClientApiError) {
    for (const [field, message] of Object.entries(error.fieldErrors ?? {})) {
      setError(field as Path<T>, { message });
    }
    setMessage(error.message);
  } else {
    setMessage("Something went wrong. Please try again.");
  }
}

const submitClass = "min-h-12 w-full rounded-xl bg-emerald-700 px-5 font-semibold text-white transition hover:bg-emerald-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 disabled:cursor-not-allowed disabled:opacity-60";
const linkClass = "font-semibold text-emerald-800 underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700";

export function LoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const requestedReturn = search.get("returnTo");
  const returnTo = requestedReturn?.startsWith("/") && !requestedReturn.startsWith("//")
    ? requestedReturn
    : "/dashboard";
  const [message, setMessage] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const form = useForm<LoginInput>({ defaultValues: { identifier: "", password: "" } });
  const submit = form.handleSubmit(async (values) => {
    setMessage("");
    const payload = validate(loginSchema, values, form.setError);
    if (!payload) return;
    try {
      await requestJson(sessionEndpoints.login, { method: "POST", body: JSON.stringify(payload) });
      router.replace(returnTo);
    } catch (error) {
      applyApiError(error, form.setError, setMessage);
    }
  });
  return (
    <form onSubmit={submit} className="space-y-5" noValidate>
      {message && <StatusPanel tone="error">{message}</StatusPanel>}
      <FormField label="Email or mobile number" autoComplete="username" required {...form.register("identifier")} error={form.formState.errors.identifier?.message} />
      <div>
        <FormField label="Password" type={showPassword ? "text" : "password"} autoComplete="current-password" required {...form.register("password")} error={form.formState.errors.password?.message} />
        <button type="button" className="mt-2 min-h-11 text-sm font-semibold text-emerald-800" onClick={() => setShowPassword((value) => !value)} aria-pressed={showPassword}>
          {showPassword ? "Hide password" : "Show password"}
        </button>
      </div>
      <div className="flex items-center justify-between gap-4 text-sm">
        <Link className={linkClass} href="/forgot-password">Forgot password?</Link>
        <Link className={linkClass} href={`/register?returnTo=${encodeURIComponent(returnTo)}`}>Create account</Link>
      </div>
      <button className={submitClass} disabled={form.formState.isSubmitting} type="submit">
        {form.formState.isSubmitting ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}

export function RegistrationForm() {
  const search = useSearchParams();
  const requestedReturn = search.get("returnTo");
  const returnTo = requestedReturn?.startsWith("/") && !requestedReturn.startsWith("//")
    ? requestedReturn
    : "/dashboard";
  const loginHref = `/login?returnTo=${encodeURIComponent(returnTo)}`;
  const [message, setMessage] = useState("");
  const [success, setSuccess] = useState(false);
  const form = useForm<RegistrationInput>({ defaultValues: { first_name: "", last_name: "", mobile_number: "", email: "", password: "", confirm_password: "", consent: false } });
  const submit = form.handleSubmit(async (values) => {
    setMessage("");
    const payload = validate(registrationSchema, values, form.setError);
    if (!payload) return;
    try {
      const { consent: _consent, ...request } = payload;
      void _consent;
      await requestJson(sessionEndpoints.register, { method: "POST", body: JSON.stringify(request) });
      setSuccess(true);
    } catch (error) {
      applyApiError(error, form.setError, setMessage);
    }
  });
  if (success) return <StatusPanel tone="success">Your account was created. Practitioner operational access still requires approval. <Link href={loginHref} className={linkClass}>Continue to sign in</Link>.</StatusPanel>;
  return (
    <form onSubmit={submit} className="space-y-5" noValidate>
      {message && <StatusPanel tone="error">{message}</StatusPanel>}
      <div className="grid gap-5 sm:grid-cols-2">
        <FormField label="First name" autoComplete="given-name" required {...form.register("first_name")} error={form.formState.errors.first_name?.message} />
        <FormField label="Last name" autoComplete="family-name" required {...form.register("last_name")} error={form.formState.errors.last_name?.message} />
      </div>
      <FormField label="Mobile number" type="tel" autoComplete="tel" required hint="Use an international number, for example +919876543210." {...form.register("mobile_number")} error={form.formState.errors.mobile_number?.message} />
      <FormField label="Email" type="email" autoComplete="email" required {...form.register("email")} error={form.formState.errors.email?.message} />
      <FormField label="Password" type="password" autoComplete="new-password" required hint="Use 12+ characters with upper/lowercase letters and a number." {...form.register("password")} error={form.formState.errors.password?.message} />
      <FormField label="Confirm password" type="password" autoComplete="new-password" required {...form.register("confirm_password")} error={form.formState.errors.confirm_password?.message} />
      <div>
        <label className="flex min-h-11 items-start gap-3 text-sm text-slate-700">
          <input type="checkbox" className="mt-1 size-5 accent-emerald-700" {...form.register("consent")} />
          <span>I agree to the Terms and Privacy notice. Final legal content will be approved separately.</span>
        </label>
        {form.formState.errors.consent?.message && <p className="mt-2 text-sm font-medium text-red-700" role="alert">{form.formState.errors.consent.message}</p>}
      </div>
      <button className={submitClass} disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? "Creating account…" : "Create account"}</button>
      <p className="text-center text-sm text-slate-600">Already registered? <Link href={loginHref} className={linkClass}>Sign in</Link></p>
    </form>
  );
}

export function ForgotPasswordForm() {
  const [message, setMessage] = useState("");
  const [success, setSuccess] = useState(false);
  const form = useForm<ForgotPasswordInput>({ defaultValues: { identifier: "" } });
  const submit = form.handleSubmit(async (values) => {
    const payload = validate(forgotPasswordSchema, values, form.setError);
    if (!payload) return;
    try {
      await requestJson(sessionEndpoints.forgotPassword, { method: "POST", body: JSON.stringify(payload) });
      setSuccess(true);
    } catch (error) { applyApiError(error, form.setError, setMessage); }
  });
  if (success) return <StatusPanel tone="success">If an eligible account exists, reset instructions are available. Delivery integration is not implemented yet.</StatusPanel>;
  return <form onSubmit={submit} className="space-y-5" noValidate>{message && <StatusPanel tone="error">{message}</StatusPanel>}<FormField label="Email or mobile number" autoComplete="username" required {...form.register("identifier")} error={form.formState.errors.identifier?.message} /><button className={submitClass} disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? "Submitting…" : "Request reset"}</button><Link className={linkClass} href="/login">Return to sign in</Link></form>;
}

export function ResetPasswordForm() {
  const search = useSearchParams();
  const [message, setMessage] = useState("");
  const [success, setSuccess] = useState(false);
  const form = useForm<ResetPasswordInput>({ defaultValues: { uid: search.get("uid") ?? "", token: search.get("token") ?? "", new_password: "", confirm_password: "" } });
  const submit = form.handleSubmit(async (values) => {
    const payload = validate(resetPasswordSchema, values, form.setError);
    if (!payload) return;
    try { await requestJson(sessionEndpoints.resetPassword, { method: "POST", body: JSON.stringify(payload) }); setSuccess(true); }
    catch (error) { applyApiError(error, form.setError, setMessage); }
  });
  if (success) return <StatusPanel tone="success">Password reset completed. <Link className={linkClass} href="/login">Sign in with your new password</Link>.</StatusPanel>;
  return <form onSubmit={submit} className="space-y-5" noValidate>{message && <StatusPanel tone="error">{message}</StatusPanel>}<FormField label="Account reset identifier" {...form.register("uid")} error={form.formState.errors.uid?.message} /><FormField label="Reset token" autoComplete="one-time-code" {...form.register("token")} error={form.formState.errors.token?.message} /><FormField label="New password" type="password" autoComplete="new-password" {...form.register("new_password")} error={form.formState.errors.new_password?.message} /><FormField label="Confirm new password" type="password" autoComplete="new-password" {...form.register("confirm_password")} error={form.formState.errors.confirm_password?.message} /><button className={submitClass} disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? "Resetting…" : "Reset password"}</button></form>;
}
