"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { requestJson } from "@/lib/api/client";
import { loadOtpWidgetConfig, sendMsg91Otp, verifyMsg91Otp, type OtpWidgetConfig } from "@/lib/auth/msg91-widget";

type Details = {
  full_name: string;
  age: string;
  gender: string;
  mobile_number: string;
  email: string;
  password: string;
  confirm_password: string;
  address_line_1: string;
  address_line_2: string;
  landmark: string;
  city: string;
  region: string;
  pin_code: string;
};

const initial: Details = {
  full_name: "", age: "", gender: "", mobile_number: "", email: "", password: "", confirm_password: "", address_line_1: "",
  address_line_2: "", landmark: "", city: "Meerut", region: "Uttar Pradesh", pin_code: "",
};

function safeReturnTo(value: string | null) {
  return value?.startsWith("/") && !value.startsWith("//") ? value : "/customer";
}

export function CustomerRegistration() {
  const router = useRouter();
  const search = useSearchParams();
  const returnTo = safeReturnTo(search.get("returnTo"));
  const [details, setDetails] = useState(initial);
  const [verificationId, setVerificationId] = useState("");
  const [config, setConfig] = useState<OtpWidgetConfig>({ enabled: false });
  const [otp, setOtp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [visible, setVisible] = useState({ password: false, confirm_password: false });

  function update(name: keyof Details, value: string) {
    setDetails((current) => ({ ...current, [name]: value }));
    if (name === "mobile_number") {
      setVerificationId("");
      setOtp("");
    }
  }

  function validateDetails() {
    if (details.full_name.trim().length < 2) return "Enter your full name.";
    if (!/^\d{1,3}$/.test(details.age) || Number(details.age) > 120) return "Enter a valid age.";
    if (!details.gender) return "Select your gender.";
    if (!/^[6-9]\d{9}$/.test(details.mobile_number)) return "Enter a valid 10-digit Indian mobile number.";
    if (!details.password) return "Enter a password.";
    if (details.password !== details.confirm_password) return "Passwords do not match.";
    if (details.address_line_1.trim().length < 5 || !details.city.trim() || !details.region.trim()) return "Enter your complete address.";
    if (!/^[1-9]\d{5}$/.test(details.pin_code)) return "Enter a valid PIN code.";
    if (Number(details.age) < 18) return "A parent or legal guardian must register and add a minor as a family member.";
    return "";
  }

  async function send() {
    const validation = validateDetails();
    if (validation) { setError(validation); return; }
    setBusy(true); setError("");
    try {
      const widget = await loadOtpWidgetConfig();
      const issued = await requestJson<{ verification_id: string }>("/api/booking-otp/issue", {
        method: "POST", body: JSON.stringify({ mobile_number: details.mobile_number }),
      });
      if (widget.enabled) await sendMsg91Otp(widget, details.mobile_number);
      setConfig(widget);
      setVerificationId(issued.verification_id);
      setOtp("");
    } catch (value) {
      setError(value instanceof Error ? value.message : "OTP could not be sent.");
    } finally { setBusy(false); }
  }

  async function complete() {
    if (!verificationId || otp.length !== 6) { setError("Enter the 6-digit OTP."); return; }
    setBusy(true); setError("");
    try {
      const providerProof = config.enabled ? { access_token: await verifyMsg91Otp(config, otp) } : { otp };
      await requestJson("/api/session/customer-register", {
        method: "POST",
        body: JSON.stringify({
          verification_id: verificationId,
          mobile_number: details.mobile_number,
          full_name: details.full_name,
          email: details.email,
          password: details.password,
          confirm_password: details.confirm_password,
          age: Number(details.age),
          gender: details.gender,
          address: {
            address_line_1: details.address_line_1,
            address_line_2: details.address_line_2,
            landmark: details.landmark,
            city: details.city,
            region: details.region,
            pin_code: details.pin_code,
          },
          ...providerProof,
        }),
      });
      router.replace(returnTo);
      router.refresh();
    } catch (value) {
      setError(value instanceof Error ? value.message : "Customer registration could not be completed.");
    } finally { setBusy(false); }
  }

  const input = (name: keyof Details, label: string, options?: { type?: string; maxLength?: number }) => (
    <label className="grid gap-2 font-semibold text-slate-800">{label}<input type={options?.type ?? "text"} maxLength={options?.maxLength} value={details[name]} onChange={(event) => update(name, event.target.value)} className="min-h-12 rounded-xl border border-slate-300 px-4 font-normal" required /></label>
  );

  return <div className="space-y-5">
    {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">{error}</p>}
    {!verificationId ? <>
      {input("full_name", "Full name")}
      <div className="grid gap-5 sm:grid-cols-2">
        {input("age", "Age", { type: "number" })}
        <label className="grid gap-2 font-semibold text-slate-800">Gender<select value={details.gender} onChange={(event) => update("gender", event.target.value)} className="min-h-12 rounded-xl border border-slate-300 px-4 font-normal" required><option value="">Select gender</option><option value="FEMALE">Female</option><option value="MALE">Male</option><option value="OTHER">Other</option><option value="PREFER_NOT_TO_SAY">Prefer not to say</option></select></label>
      </div>
      {input("mobile_number", "Mobile number", { type: "tel", maxLength: 10 })}
      {input("email", "Email (optional)", { type: "email" })}
      {(["password", "confirm_password"] as const).map((name) => <label key={name} className="grid gap-2 font-semibold text-slate-800">{name === "password" ? "Password" : "Confirm password"}<span className="flex rounded-xl border border-slate-300 bg-white focus-within:ring-2 focus-within:ring-emerald-600"><input type={visible[name] ? "text" : "password"} autoComplete="new-password" value={details[name]} onChange={(event) => update(name, event.target.value)} className="min-h-12 min-w-0 flex-1 rounded-xl px-4 outline-none" required /><button type="button" onClick={() => setVisible((current) => ({ ...current, [name]: !current[name] }))} className="px-4 text-sm font-semibold text-emerald-800" aria-label={visible[name] ? `Hide ${name === "password" ? "password" : "confirmation password"}` : `Show ${name === "password" ? "password" : "confirmation password"}`}>{visible[name] ? "Hide" : "Show"}</button></span></label>)}
      {input("address_line_1", "Address")}
      {input("address_line_2", "Address line 2 (optional)")}
      {input("landmark", "Landmark (optional)")}
      <div className="grid gap-5 sm:grid-cols-2">{input("city", "City")}{input("region", "State / region")}</div>
      {input("pin_code", "PIN code", { maxLength: 6 })}
      <button type="button" disabled={busy} onClick={send} className="button-primary w-full disabled:opacity-50">{busy ? "Sending…" : "Send OTP"}</button>
    </> : <>
      <p className="text-sm text-slate-600">Enter the OTP sent to your registered mobile number.</p>
      <label className="grid gap-2 font-semibold text-slate-800">One-time password<input inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={otp} onChange={(event) => setOtp(event.target.value.replace(/\D/g, ""))} className="min-h-12 rounded-xl border border-slate-300 px-4 tracking-[0.4em]" /></label>
      <button type="button" disabled={busy || otp.length !== 6} onClick={complete} className="button-primary w-full disabled:opacity-50">{busy ? "Registering…" : "Verify and create account"}</button>
      <button type="button" disabled={busy} onClick={send} className="button-secondary w-full disabled:opacity-50">Resend OTP</button>
      <button type="button" onClick={() => { setVerificationId(""); setOtp(""); }} className="min-h-11 w-full font-semibold text-emerald-800">Edit details</button>
    </>}
    <p className="text-center text-sm text-slate-600">Already registered? <Link className="font-semibold text-emerald-800" href={`/customer-login?returnTo=${encodeURIComponent(returnTo)}`}>Customer Login</Link></p>
  </div>;
}
