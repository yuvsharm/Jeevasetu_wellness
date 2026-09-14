"use client";

import Link from "next/link";
import { useState } from "react";

import { OtpInput, OtpResendButton } from "@/components/auth/otp-input";
import { PasswordCreationFields, isStrongPassword } from "@/components/auth/password-creation-fields";
import { loadOtpWidgetConfig, sendMsg91Otp, verifyMsg91Otp, type OtpWidgetConfig } from "@/lib/auth/msg91-widget";
import { requestJson } from "@/lib/api/client";

export function TherapistSecurity({ mobile }: { mobile: string }) {
  const [mode, setMode] = useState<"" | "mobile" | "password">("");
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [number, setNumber] = useState("");
  const [id, setId] = useState("");
  const [otp, setOtp] = useState("");
  const [config, setConfig] = useState<OtpWidgetConfig>({ enabled: false });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function perform(task: () => Promise<void>) {
    setBusy(true);
    setMessage("");
    try { await task(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "The request could not be completed."); }
    finally { setBusy(false); }
  }

  async function issueOtp() {
    const nextConfig = await loadOtpWidgetConfig();
    const issued = await requestJson<{ verification_id: string }>("/api/booking-otp/issue", {
      method: "POST", body: JSON.stringify({ mobile_number: number }),
    });
    if (nextConfig.enabled) await sendMsg91Otp(nextConfig, number);
    setConfig(nextConfig);
    setId(issued.verification_id);
  }

  async function done() {
    setCurrent(""); setNext(""); setConfirm(""); setOtp("");
    await requestJson("/api/session/logout", { method: "POST" });
    window.location.assign("/therapist-login");
  }

  return <div className="mt-4 space-y-4">
    <p>Verified mobile: <strong>{mobile}</strong></p>
    <div className="flex flex-wrap gap-3">
      <button className="button-secondary" onClick={() => { setMode("mobile"); setId(""); }}>Change Mobile via OTP</button>
      <button className="button-secondary" onClick={() => setMode("password")}>Change Password</button>
      <Link className="button-secondary" href="/forgot-password?context=therapist">Forgot Password?</Link>
    </div>
    {mode && <div className="max-w-lg space-y-3 rounded-xl bg-slate-50 p-4">
      <label className="grid min-w-0 gap-2">Current password
        <input type="password" autoComplete="current-password" value={current} onChange={(event) => setCurrent(event.target.value)} className="min-h-12 w-full min-w-0 rounded-xl border px-3" />
      </label>
      {mode === "password" ? <form onSubmit={(event) => { event.preventDefault(); void perform(async () => {
        await requestJson("/api/session/change-password", { method: "POST", body: JSON.stringify({ old_password: current, new_password: next, confirm_password: confirm }) });
        await done();
      }); }}>
        <PasswordCreationFields password={next} confirmPassword={confirm} onPasswordChange={setNext} onConfirmPasswordChange={setConfirm} />
        <button className="button-primary mt-3" disabled={busy || !current || !isStrongPassword(next) || next !== confirm}>Save Password</button>
      </form> : <>
        <label className="grid min-w-0 gap-2">New registered mobile
          <input value={number} maxLength={10} inputMode="numeric" autoComplete="tel" onChange={(event) => { setNumber(event.target.value.replace(/\D/g, "")); setId(""); setOtp(""); }} className="min-h-12 w-full min-w-0 rounded-xl border px-3" />
        </label>
        <p className="text-sm">Enter a valid 10-digit Indian mobile number.</p>
        <button className="button-secondary" disabled={busy || !current || !/^[6-9]\d{9}$/.test(number) || Boolean(id)} onClick={() => void perform(issueOtp)}>Send OTP</button>
        {id && <>
          <OtpInput label="OTP for new mobile" mobileNumber={number} value={otp} onChange={setOtp} />
          <button className="button-primary" disabled={busy || otp.length !== 6} onClick={() => void perform(async () => {
            const provider = config.enabled ? { access_token: await verifyMsg91Otp(config, otp) } : { otp };
            const proof = await requestJson<{ token: string }>("/api/booking-otp/verify", { method: "POST", body: JSON.stringify({ verification_id: id, mobile_number: number, ...provider }) });
            await requestJson("/api/staff/me/change-mobile", { method: "POST", body: JSON.stringify({ mobile_number: number, current_password: current, booking_verification_token: proof.token }) });
            await done();
          })}>Verify and Change Mobile</button>
          <OtpResendButton busy={busy} onResend={() => perform(issueOtp)} />
        </>}
      </>}
      <button className="button-secondary" onClick={() => { setMode(""); setCurrent(""); setOtp(""); setNext(""); setConfirm(""); }}>Cancel</button>
    </div>}
    {message && <p role="alert" className="text-red-700">{message}</p>}
  </div>;
}
