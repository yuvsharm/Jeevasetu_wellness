"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { isStrongPassword, PasswordCreationFields } from "@/components/auth/password-creation-fields";
import { OtpInput, OtpResendButton } from "@/components/auth/otp-input";
import { requestJson } from "@/lib/api/client";
import { loadOtpWidgetConfig, sendMsg91Otp, verifyMsg91Otp, type OtpWidgetConfig } from "@/lib/auth/msg91-widget";

type Stage = "mobile" | "otp" | "password" | "done";

export function CustomerPasswordReset({context="customer"}:{context?:"customer"|"therapist"|"staff"}) {
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const normalizeMobile = (value: string) => {
    const digits = value.replace(/\D/g, "");
    return digits.length === 12 && digits.startsWith("91") ? digits.slice(2) : digits.slice(0, 10);
  };

  async function send() {
    if(!/^[6-9]\d{9}$/.test(mobile)){setError("Enter a valid 10-digit Indian mobile number.");return;}
    setBusy(true); setError(""); setAccessToken("");
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
      const proof=config.enabled?{access_token:await verifyMsg91Otp(config,otp)}:{otp};
      const verified=await requestJson<{token:string}>("/api/booking-otp/verify",{method:"POST",body:JSON.stringify({verification_id:verificationId,mobile_number:mobile,...proof})});
      setAccessToken(verified.token);
      setStage("password");
    } catch (value) { setError(value instanceof Error ? value.message : "OTP could not be verified."); }
    finally { setBusy(false); }
  }

  async function reset(event: React.FormEvent) {
    event.preventDefault();
    if (!isStrongPassword(password)) { setError("Password does not meet all requirements."); return; }
    if (password !== confirm) { setError("Passwords do not match."); return; }
    setBusy(true); setError("");
    try {
      await requestJson(context==="customer"?"/api/session/customer-password-reset":"/api/session/account-password-reset", { method: "POST", body: JSON.stringify({ verification_id: verificationId, mobile_number: mobile, booking_verification_token:accessToken, new_password: password, confirm_password: confirm }) });
      setOtp(""); setAccessToken(""); setPassword(""); setConfirm(""); setStage("done");
    } catch (value) { setError(value instanceof Error ? value.message : "Password reset could not be completed."); }
    finally { setBusy(false); }
  }

  if (stage === "done") return <div className="space-y-5"><p role="status" className="rounded-xl bg-emerald-50 p-3 text-emerald-900">Password reset successfully. Please sign in with your new password.</p><Link className="button-primary block text-center" href={context==="customer"?`/customer-login?returnTo=${encodeURIComponent(returnTo)}`:context==="therapist"?"/therapist-login":"/login"}>Sign in</Link></div>;
  return <div className="space-y-5">
    <p className="text-sm text-slate-600">Enter your registered 10-digit Indian mobile number.</p>
    {stage!=="mobile"&&<button type="button" disabled={busy} className="button-secondary" onClick={()=>{setStage("mobile");setAccessToken("");setOtp("");setPassword("");setConfirm("");setError("")}}>Change mobile number / Start again</button>}
    {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">{error}</p>}
    {stage === "mobile" && <><label className="grid gap-2 font-semibold text-slate-800">Mobile number<input inputMode="tel" autoComplete="tel" maxLength={13} value={mobile} onChange={(event) => setMobile(normalizeMobile(event.target.value))} className="min-h-12 rounded-xl border border-slate-300 px-4" required /></label><button disabled={busy || mobile.length !== 10} onClick={send} className="button-primary w-full disabled:opacity-50">{busy ? "Sending…" : "Send OTP"}</button></>}
    {stage === "otp" && <><OtpInput value={otp} onChange={setOtp} mobileNumber={mobile}/><button disabled={busy || otp.length !== 6} onClick={verify} className="button-primary w-full disabled:opacity-50">{busy ? "Verifying…" : "Verify mobile"}</button><OtpResendButton busy={busy} onResend={send}/></>}
    {stage === "password" && <form className="space-y-5" onSubmit={reset}><PasswordCreationFields password={password} confirmPassword={confirm} onPasswordChange={setPassword} onConfirmPasswordChange={setConfirm} passwordLabel="New password" confirmLabel="Confirm new password"/><button disabled={busy || !isStrongPassword(password) || password !== confirm} className="button-primary w-full disabled:opacity-50">{busy ? "Resetting…" : "Reset password"}</button></form>}
  </div>;
}
