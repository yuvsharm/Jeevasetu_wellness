"use client";

import { useEffect, useId, useRef, useState } from "react";

type OtpCredential = Credential & { code: string };
type OtpCredentialRequestOptions = CredentialRequestOptions & { otp?: { transport: string[] } };

function normalize(value: string) {
  return value.replace(/\D/g, "").slice(0, 6);
}

export function maskMobile(value?: string) {
  const digits = value?.replace(/\D/g, "") ?? "";
  return digits.length >= 4 ? `••••••${digits.slice(-4)}` : "your mobile number";
}

export function OtpInput({ value, onChange, label = "One-time password", mobileNumber, enabled = true, className = "min-h-12 w-full min-w-0 rounded-xl border border-slate-300 px-4 tracking-[0.35em] outline-none focus:border-emerald-700 focus:ring-4 focus:ring-emerald-100" }:{
  value: string; onChange: (value: string) => void; label?: string; mobileNumber?: string; enabled?: boolean; className?: string;
}) {
  const id = useId();
  const webOtpStatus = useOtpAutofill(enabled, onChange);
  return <div className="grid min-w-0 gap-2">
    <label htmlFor={id} className="font-semibold text-slate-800">{label}</label>
    {mobileNumber && <p className="text-sm text-slate-600">Sent to <strong>{maskMobile(mobileNumber)}</strong></p>}
    <input id={id} aria-describedby={`${id}-help`} aria-invalid={value.length > 0 && value.length !== 6} type="text" inputMode="numeric" autoComplete="one-time-code" enterKeyHint="done" pattern="[0-9]{6}" maxLength={6} value={value} onChange={(event) => onChange(normalize(event.target.value))} onPaste={(event) => { const code = normalize(event.clipboardData.getData("text")); if (code) { event.preventDefault(); onChange(code); } }} className={className}/>
    <p id={`${id}-help`} className="text-xs font-normal text-slate-600">Enter the 6-digit code. You can paste the complete code. It expires 10 minutes after it is sent.</p>
    {webOtpStatus !== "idle" && <span role="status" aria-live="polite" className="text-xs font-normal text-slate-600">{webOtpStatus === "waiting" ? "Waiting for a compatible SMS code… Manual entry is always available." : "SMS code detected. Review it, then verify."}</span>}
  </div>;
}

export function OtpResendButton({ onResend, busy = false, cooldownSeconds = 30 }:{ onResend: () => void | Promise<void>; busy?: boolean; cooldownSeconds?: number }) {
  const [seconds, setSeconds] = useState(cooldownSeconds);
  const [sending, setSending] = useState(false);
  useEffect(() => {
    if (seconds <= 0) return;
    const timer = window.setInterval(() => setSeconds((current) => Math.max(0, current - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [seconds]);
  return <button type="button" disabled={busy || sending || seconds > 0} onClick={async () => { setSending(true); try { await onResend(); setSeconds(cooldownSeconds); } finally { setSending(false); } }} className="button-secondary w-full disabled:cursor-not-allowed disabled:opacity-50">{sending ? "Sending…" : seconds > 0 ? `Resend code in 0:${String(seconds).padStart(2, "0")}` : "Resend OTP"}</button>;
}

export function useOtpAutofill(enabled: boolean, onChange: (value:string)=>void) {
  const supported = enabled && typeof window !== "undefined" && window.isSecureContext && "OTPCredential" in window && Boolean(navigator.credentials);
  const [detected, setDetected] = useState(false);
  const onChangeRef = useRef(onChange);
  useEffect(() => { onChangeRef.current = onChange; }, [onChange]);
  useEffect(() => {
    if (!supported) return;
    const controller = new AbortController();
    navigator.credentials.get({ otp: { transport: ["sms"] }, signal: controller.signal } as OtpCredentialRequestOptions)
      .then((credential) => {
        const code = normalize((credential as OtpCredential | null)?.code ?? "");
        if (code) { onChangeRef.current(code); setDetected(true); }
      }).catch(() => undefined);
    return () => controller.abort();
  }, [supported]);
  return supported ? detected ? "detected" : "waiting" : "idle";
}
