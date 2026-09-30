"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import {useQueryClient} from "@tanstack/react-query";

import { isStrongPassword, PasswordCreationFields } from "@/components/auth/password-creation-fields";
import { OtpInput, OtpResendButton } from "@/components/auth/otp-input";
import type {Session} from "@/lib/api/contracts";
import { ClientApiError, requestJson } from "@/lib/api/client";
import {establishAuthenticatedSession} from "@/lib/auth/session-cache";
import { loadOtpWidgetConfig, sendMsg91Otp, verifyMsg91Otp, type OtpWidgetConfig } from "@/lib/auth/msg91-widget";

const fieldClass = "min-h-12 rounded-xl border border-slate-300 px-4 font-normal";

export function PractitionerLogin() {
  const router = useRouter();
  const queryClient=useQueryClient();
  const search = useSearchParams();
  const [mobile, setMobile] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault(); if(!/^[6-9]\d{9}$/.test(mobile)){setError("Enter a valid 10-digit Indian mobile number.");return;} setBusy(true); setError("");
    try {
      const session=await requestJson<Session>("/api/session/login", { method:"POST", body:JSON.stringify({ identifier:mobile, password }) });
      await establishAuthenticatedSession(queryClient,session);
      router.replace(search.get("returnTo")?.startsWith("/") ? search.get("returnTo")! : "/dashboard");
      router.refresh();
    } catch (value) { setError(value instanceof ClientApiError && value.status===401 ? "Invalid mobile number or password." : value instanceof Error ? value.message : "Sign in failed."); }
    finally { setBusy(false); }
  }
  return <form onSubmit={submit} className="space-y-5">
    {search.get("registered")&&<p role="status" className="rounded-xl bg-emerald-50 p-3 text-emerald-900">Account ready. Sign in to continue your practitioner application.</p>}
    {error&&<p role="alert" className="rounded-xl bg-red-50 p-3 text-red-800">{error}</p>}
    <p className="text-sm text-slate-600">Enter your registered 10-digit Indian mobile number.</p><label className="grid gap-2 font-semibold">Mobile number<input inputMode="numeric" autoComplete="tel" maxLength={10} value={mobile} onChange={e=>setMobile(e.target.value.replace(/\D/g,""))} className={fieldClass} required/></label>
    <label className="grid gap-2 font-semibold">Password<span className="flex rounded-xl border border-slate-300"><input type={show?"text":"password"} autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} className="min-h-12 min-w-0 flex-1 rounded-xl px-4 outline-none" required/><button type="button" onClick={()=>setShow(!show)} className="px-4 text-sm font-semibold text-emerald-800">{show?"Hide":"Show"}</button></span></label>
    <div className="grid grid-cols-2 gap-3 text-sm"><Link href="/forgot-password?context=therapist" className="font-semibold text-emerald-800">Forgot Password?</Link><Link href="/therapist-activate" className="text-right font-semibold text-emerald-800">Activate Account</Link><Link href="/therapist-register" className="col-span-2 text-center font-semibold text-emerald-800">New practitioner? Apply to Join</Link></div>
    <button disabled={busy||!/^[6-9]\d{9}$/.test(mobile)||!password} className="button-primary w-full disabled:opacity-50">{busy?"Signing in…":"Sign In"}</button>
  </form>;
}

export function PractitionerActivation() {
  const [stage,setStage]=useState<"mobile"|"otp"|"password"|"done">("mobile");
  const [mobile,setMobile]=useState(""); const [verificationId,setVerificationId]=useState(""); const [token,setToken]=useState("");
  const [otp,setOtp]=useState(""); const [password,setPassword]=useState(""); const [confirm,setConfirm]=useState("");
  const [config,setConfig]=useState<OtpWidgetConfig>({enabled:false}); const [busy,setBusy]=useState(false); const [error,setError]=useState("");
  async function send(){if(!/^[6-9]\d{9}$/.test(mobile)){setError("Enter the 10-digit mobile number registered by NuriPain Ease.");return;}setBusy(true);setError("");try{const widget=await loadOtpWidgetConfig();const issued=await requestJson<{verification_id:string}>("/api/booking-otp/issue",{method:"POST",body:JSON.stringify({mobile_number:mobile})});if(widget.enabled)await sendMsg91Otp(widget,mobile);setConfig(widget);setVerificationId(issued.verification_id);setStage("otp");}catch(value){setError(value instanceof Error?value.message:"OTP could not be sent.");}finally{setBusy(false)}}
  async function verify(){setBusy(true);setError("");try{const proof=config.enabled?{access_token:await verifyMsg91Otp(config,otp)}:{otp};const value=await requestJson<{token:string}>("/api/booking-otp/verify",{method:"POST",body:JSON.stringify({verification_id:verificationId,mobile_number:mobile,...proof})});setToken(value.token);setOtp("");setStage("password");}catch(value){setError(value instanceof Error?value.message:"Mobile verification failed.");}finally{setBusy(false)}}
  async function activate(event:React.FormEvent){event.preventDefault();if(!isStrongPassword(password)){setError("Password does not meet all requirements.");return;}if(password!==confirm){setError("Passwords do not match.");return;}setBusy(true);setError("");try{await requestJson("/api/session/practitioner-activate",{method:"POST",body:JSON.stringify({mobile_number:mobile,full_name:"Account Activation",booking_verification_token:token,password,confirm_password:confirm})});setStage("done");}catch(value){setError(value instanceof Error?value.message:"Account activation could not be completed.");}finally{setBusy(false)}}
  if(stage==="done")return <div className="space-y-5"><p role="status" className="rounded-xl bg-emerald-50 p-3 text-emerald-900">Activation successful. Your password is ready.</p><Link href="/therapist-login?activated=1" className="button-primary block text-center">Go to Therapist Login</Link></div>;
  return <div className="space-y-5">{error&&<p role="alert" className="rounded-xl bg-red-50 p-3 text-red-800">{error}</p>}{stage==="mobile"&&<><p className="text-sm text-slate-600">For therapists whose account was created by a NuriPain Ease Owner. You will verify your registered mobile and choose your own password.</p><label className="grid gap-2 font-semibold">Registered mobile number<input className={fieldClass} inputMode="numeric" autoComplete="tel" maxLength={10} value={mobile} onChange={e=>setMobile(e.target.value.replace(/\D/g,""))}/></label><button onClick={send} disabled={busy||mobile.length!==10} className="button-primary w-full disabled:opacity-50">{busy?"Sending…":"Send OTP"}</button></>}{stage==="otp"&&<><OtpInput value={otp} onChange={setOtp} mobileNumber={mobile}/><button onClick={verify} disabled={busy||otp.length!==6} className="button-primary w-full disabled:opacity-50">{busy?"Verifying…":"Verify Mobile"}</button><OtpResendButton busy={busy} onResend={send}/></>}{stage==="password"&&<form onSubmit={activate} className="space-y-5"><p role="status" className="rounded-xl bg-emerald-50 p-3 text-emerald-900">Mobile number verified. Create a password known only to you.</p><PasswordCreationFields password={password} confirmPassword={confirm} onPasswordChange={setPassword} onConfirmPasswordChange={setConfirm} passwordLabel="Set Password" confirmLabel="Confirm Password"/><button disabled={busy||!isStrongPassword(password)||password!==confirm} className="button-primary w-full disabled:opacity-50">{busy?"Activating…":"Activate Account"}</button></form>}<Link href="/therapist-login" className="block text-center text-sm font-semibold text-emerald-800">Back to Therapist Login</Link></div>;
}

export { PractitionerRegistration } from "@/components/practitioners/self-registration";
