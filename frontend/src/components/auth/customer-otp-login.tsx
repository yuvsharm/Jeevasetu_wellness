"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { requestJson } from "@/lib/api/client";

type Issued = { verification_id: string; otp?: string; message: string };

export function CustomerOtpLogin() {
  const router = useRouter();
  const [mobile, setMobile] = useState("");
  const [otp, setOtp] = useState("");
  const [issued, setIssued] = useState<Issued | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function issue() {
    setBusy(true); setError("");
    try { setIssued(await requestJson<Issued>("/api/booking-otp/issue", { method: "POST", body: JSON.stringify({ mobile_number: mobile }) })); }
    catch (value) { setError(value instanceof Error ? value.message : "OTP could not be sent."); }
    finally { setBusy(false); }
  }
  async function verify() {
    if (!issued) return;
    setBusy(true); setError("");
    try {
      await requestJson("/api/session/customer-login", { method: "POST", body: JSON.stringify({ verification_id: issued.verification_id, mobile_number: mobile, otp }) });
      router.replace("/customer"); router.refresh();
    } catch (value) { setError(value instanceof Error ? value.message : "OTP could not be verified."); }
    finally { setBusy(false); }
  }
  return <div className="space-y-5">
    {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">{error}</p>}
    <label className="grid gap-2 font-semibold text-slate-800">Mobile number<input inputMode="numeric" autoComplete="tel" maxLength={10} value={mobile} onChange={(e) => setMobile(e.target.value.replace(/\D/g, ""))} className="min-h-12 rounded-xl border border-slate-300 px-4" placeholder="10-digit mobile number" /></label>
    {!issued ? <button disabled={busy || mobile.length !== 10} onClick={issue} className="min-h-12 w-full rounded-xl bg-emerald-700 px-5 font-bold text-white disabled:opacity-50">{busy ? "Sending…" : "Send OTP"}</button> : <>
      <p className="text-sm text-slate-600">{issued.message}{issued.otp ? ` Development OTP: ${issued.otp}` : ""}</p>
      <label className="grid gap-2 font-semibold text-slate-800">One-time password<input inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={otp} onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))} className="min-h-12 rounded-xl border border-slate-300 px-4 tracking-[0.4em]" /></label>
      <button disabled={busy || otp.length !== 6} onClick={verify} className="min-h-12 w-full rounded-xl bg-emerald-700 px-5 font-bold text-white disabled:opacity-50">{busy ? "Verifying…" : "Open customer dashboard"}</button>
      <button onClick={() => { setIssued(null); setOtp(""); }} className="min-h-11 w-full font-semibold text-emerald-800">Use another number</button>
    </>}
  </div>;
}
