"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { useSession } from "@/components/auth/session-provider";
import { LoadingState, StatusPanel } from "@/components/feedback/status-panel";
import { FormField } from "@/components/forms/form-field";
import { AppShell } from "@/components/shell/app-shell";
import type { Session, UserSummary } from "@/lib/api/contracts";
import { ClientApiError, requestJson } from "@/lib/api/client";
import { sessionEndpoints } from "@/lib/api/endpoints";
import { primaryRole } from "@/lib/auth/roles";
import { profileSchema, type ProfileInput } from "@/lib/forms/schemas";

export function ProfilePage() {
  const session = useSession();
  const queryClient = useQueryClient();
  const [message, setMessage] = useState("");
  const [saved, setSaved] = useState(false);
  const form = useForm<ProfileInput>({ values: session.data ? { first_name: session.data.user.first_name, last_name: session.data.user.last_name, email: session.data.user.email, mobile_number: session.data.user.mobile_number } : undefined });
  if (session.isPending) return <LoadingState />;
  if (!session.data) return <main className="p-8"><StatusPanel tone="error">Your profile is unavailable.</StatusPanel></main>;
  const role = primaryRole(session.data.access.roles);
  if (!role) return <main className="p-8"><StatusPanel tone="error">No active role is available.</StatusPanel></main>;
  const submit = form.handleSubmit(async (values) => {
    setMessage(""); setSaved(false);
    const parsed = profileSchema.safeParse(values);
    if (!parsed.success) { for (const issue of parsed.error.issues) { const field = issue.path[0]; if (typeof field === "string") form.setError(field as keyof ProfileInput, { message: issue.message }); } return; }
    try {
      const user = await requestJson<UserSummary>(sessionEndpoints.profile, { method: "PATCH", body: JSON.stringify(parsed.data) });
      queryClient.setQueryData<Session>(["session"], { ...session.data, user });
      setSaved(true);
    } catch (error) { setMessage(error instanceof ClientApiError ? error.message : "Profile update failed."); }
  });
  return <AppShell session={session.data} role={role} title="Profile"><section className="max-w-2xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8"><h2 className="text-2xl font-bold text-slate-950">Account details</h2><p className="mt-2 text-slate-600">Only identity fields supported by the current backend can be changed.</p><div className="mt-5 rounded-xl bg-slate-50 p-4 text-sm text-slate-700"><p><strong>Account access:</strong> Active and backend validated</p><p className="mt-1"><strong>Active role:</strong> {role}</p><p className="mt-1"><strong>Organization:</strong> {session.data.access.organization.slug}</p><p className="mt-1"><strong>Clinics:</strong> {session.data.access.permitted_clinics.map((clinic) => clinic.slug).join(", ") || "No clinic scope"}</p></div><form onSubmit={submit} className="mt-7 space-y-5" noValidate>{message && <StatusPanel tone="error">{message}</StatusPanel>}{saved && <StatusPanel tone="success">Profile updated.</StatusPanel>}<div className="grid gap-5 sm:grid-cols-2"><FormField label="First name" {...form.register("first_name")} error={form.formState.errors.first_name?.message} /><FormField label="Last name" {...form.register("last_name")} error={form.formState.errors.last_name?.message} /></div><FormField label="Email" type="email" {...form.register("email")} error={form.formState.errors.email?.message} /><FormField label="Mobile number" type="tel" {...form.register("mobile_number")} error={form.formState.errors.mobile_number?.message} /><button className="min-h-12 rounded-xl bg-emerald-700 px-6 font-semibold text-white disabled:opacity-60" disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? "Saving…" : "Save profile"}</button></form></section></AppShell>;
}
