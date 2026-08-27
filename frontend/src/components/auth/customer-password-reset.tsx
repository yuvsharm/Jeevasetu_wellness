"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { requestJson } from "@/lib/api/client";
import { loadOtpWidgetConfig, sendMsg91Otp, verifyMsg91Otp, type OtpWidgetConfig } from "@/lib/auth/msg91-widget";

type Stage = "mobile" | "otp" | "password" | "done";

export function CustomerPasswordReset() {
  const search = useSearchParams();
  const returnTo = search.get("returnTo")?.startsWith("/") && !search.get("returnTo")?.startsWith("//") ? search.get("returnTo")! : "/customer";
  const [stage, setStage] = useState<Stage>("mobile");
  const [mobile, setMobile] = useState("");
  const [verificationId, setVerificationId] = useState("");
  const [config, setConfig] = useState<OtpWidgetConfig>({ enabled: false });
  const [otp, setOtp] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState({ password: false, confirm: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function send() {
    setBusy(true); setError("");
    try {
      const widget = await loadOtpWidgetConfig();
      const issued = await requestJson<{ verification_id: string }>("/api/booking-otp/issue", { method: "POST", body: JSON.stringify({ mobile_number: mobile }) });
      if (widget.enabled) await sendMsg91Otp(widget, mobile);
      setConfig(widget); setVerificationId(issued.verification_id); setOtp(""); setStage("otp");
    } catch (value) { setError(value instanceof Error ? value.message : "OTP could not be sent."); }
    finally { setBusy(false); }
  }

  async function verify() {
    setBusy(true); setError("");
    try {
      if (config.enabled) setAccessToken(await verifyMsg91Otp(config, otp));
      setStage("password");
    } catch (value) { setError(value instanceof Error ? value.message : "OTP could not be verified."); }
    finally { setBusy(false); }
  }

  async function reset(event: React.FormEvent) {
    event.preventDefault();
    if (password !== confirm) { setError("Passwords do not match."); return; }
    setBusy(true); setError("");
    try {
      await requestJson("/api/session/customer-password-reset", { method: "POST", body: JSON.stringify({ verification_id: verificationId, mobile_number: mobile, ...(config.enabled ? { access_token: accessToken } : { otp }), new_password: password, confirm_password: confirm }) });
      setOtp(""); setAccessToken(""); setStage("done");
    } catch (value) { setError(value instanceof Error ? value.message : "Password reset could not be completed."); }
    finally { setBusy(false); }
  }

  if (stage === "done") return <div className="space-y-5"><p role="status" className="rounded-xl bg-emerald-50 p-3 text-emerald-900">Your password has been reset.</p><Link className="button-primary block text-center" href={`/customer-login?returnTo=${encodeURIComponent(returnTo)}`}>Sign in</Link></div>;
  return <div className="space-y-5">
    {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">{error}</p>}
    {stage === "mobile" && <><label className="grid gap-2 font-semibold text-slate-800">Mobile number<input inputMode="numeric" autoComplete="tel" maxLength={10} value={mobile} onChange={(event) => setMobile(event.target.value.replace(/\D/g, ""))} className="min-h-12 rounded-xl border border-slate-300 px-4" required /></label><button disabled={busy || mobile.length !== 10} onClick={send} className="button-primary w-full disabled:opacity-50">{busy ? "Sending…" : "Send OTP"}</button></>}
    {stage === "otp" && <><label className="grid gap-2 font-semibold text-slate-800">One-time password<input inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={otp} onChange={(event) => setOtp(event.target.value.replace(/\D/g, ""))} className="min-h-12 rounded-xl border border-slate-300 px-4 tracking-[0.4em]" /></label><button disabled={busy || otp.length !== 6} onClick={verify} className="button-primary w-full disabled:opacity-50">{busy ? "Verifying…" : "Verify mobile"}</button><button disabled={busy} onClick={send} className="button-secondary w-full">Resend OTP</button></>}
    {stage === "password" && <form className="space-y-5" onSubmit={reset}>{(["password", "confirm"] as const).map((name) => <label key={name} className="grid gap-2 font-semibold text-slate-800">{name === "password" ? "New password" : "Confirm new password"}<span className="flex rounded-xl border border-slate-300"><input type={show[name] ? "text" : "password"} autoComplete="new-password" value={name === "password" ? password : confirm} onChange={(event) => name === "password" ? setPassword(event.target.value) : setConfirm(event.target.value)} className="min-h-12 min-w-0 flex-1 rounded-xl px-4 outline-none" required /><button type="button" onClick={() => setShow((current) => ({ ...current, [name]: !current[name] }))} className="px-4 text-sm font-semibold text-emerald-800" aria-label={show[name] ? "Hide password" : "Show password"}>{show[name] ? "Hide" : "Show"}</button></span></label>)}<button disabled={busy || !password || !confirm} className="button-primary w-full disabled:opacity-50">{busy ? "Resetting…" : "Reset password"}</button></form>}
  </div>;
}
