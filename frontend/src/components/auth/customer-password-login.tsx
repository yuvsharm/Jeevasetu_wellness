"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import type { Session } from "@/lib/api/contracts";
import { requestJson } from "@/lib/api/client";
import { establishAuthenticatedSession } from "@/lib/auth/session-cache";

function safeReturnTo(value: string | null) {
  return value?.startsWith("/") && !value.startsWith("//") ? value : "/customer";
}

export function CustomerPasswordLogin() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const search = useSearchParams();
  const returnTo = safeReturnTo(search.get("returnTo"));
  const registered = search.get("registered") === "1";
  const expired = search.get("reason") === "expired";
  const [mobile, setMobile] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const session = await requestJson<Session>("/api/session/customer-login", {
        method: "POST",
        body: JSON.stringify({ mobile_number: mobile, password }),
      });
      await establishAuthenticatedSession(queryClient, session);
      router.replace(returnTo);
      router.refresh();
    } catch (value) {
      setError(value instanceof Error ? value.message : "Sign in could not be completed.");
    } finally {
      setBusy(false);
    }
  }

  return <form className="space-y-5" onSubmit={submit}>
    {registered && <p role="status" className="rounded-xl bg-emerald-50 p-3 text-sm font-semibold text-emerald-900">Account created successfully. Please sign in.</p>}
    {expired && <p role="status" className="rounded-xl bg-amber-50 p-3 text-sm font-semibold text-amber-900">Your customer session has expired. Please sign in again.</p>}
    {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">{error}</p>}
    <label className="grid gap-2 font-semibold text-slate-800">Mobile number<input inputMode="numeric" autoComplete="tel" maxLength={10} value={mobile} onChange={(event) => setMobile(event.target.value.replace(/\D/g, ""))} className="min-h-12 rounded-xl border border-slate-300 px-4" placeholder="10-digit mobile number" required /></label>
    <label className="grid gap-2 font-semibold text-slate-800">Password<span className="flex rounded-xl border border-slate-300 bg-white focus-within:ring-2 focus-within:ring-emerald-600"><input type={showPassword ? "text" : "password"} autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} className="min-h-12 min-w-0 flex-1 rounded-xl px-4 outline-none" required /><button type="button" onClick={() => setShowPassword((value) => !value)} className="px-4 text-sm font-semibold text-emerald-800" aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? "Hide" : "Show"}</button></span></label>
    <div className="text-right"><Link className="text-sm font-semibold text-emerald-800" href={`/customer-forgot-password?returnTo=${encodeURIComponent(returnTo)}`}>Forgot password?</Link></div>
    <button disabled={busy || mobile.length !== 10 || !password} className="button-primary w-full disabled:opacity-50">{busy ? "Signing in…" : "Open customer dashboard"}</button>
  </form>;
}
