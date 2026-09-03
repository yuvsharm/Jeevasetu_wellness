"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { isStrongPassword, PasswordCreationFields } from "@/components/auth/password-creation-fields";
import { requestJson } from "@/lib/api/client";
import { loadOtpWidgetConfig, sendMsg91Otp, verifyMsg91Otp, type OtpWidgetConfig } from "@/lib/auth/msg91-widget";

const fieldClass = "min-h-12 rounded-xl border border-slate-300 px-4 font-normal";

export function PractitionerLogin() {
  const router = useRouter();
  const search = useSearchParams();
  const [mobile, setMobile] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await requestJson("/api/session/login", { method:"POST", body:JSON.stringify({ identifier:mobile, password }) });
      router.replace(search.get("returnTo")?.startsWith("/") ? search.get("returnTo")! : "/dashboard");
      router.refresh();
    } catch (value) { setError(value instanceof Error ? value.message : "Sign in failed."); }
    finally { setBusy(false); }
  }
  return <form onSubmit={submit} className="space-y-5">
    {search.get("registered")&&<p role="status" className="rounded-xl bg-emerald-50 p-3 text-emerald-900">Account ready. Sign in to continue your practitioner application.</p>}
    {error&&<p role="alert" className="rounded-xl bg-red-50 p-3 text-red-800">{error}</p>}
    <label className="grid gap-2 font-semibold">Mobile number<input inputMode="numeric" autoComplete="tel" maxLength={10} value={mobile} onChange={e=>setMobile(e.target.value.replace(/\D/g,""))} className={fieldClass} required/></label>
    <label className="grid gap-2 font-semibold">Password<span className="flex rounded-xl border border-slate-300"><input type={show?"text":"password"} autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} className="min-h-12 min-w-0 flex-1 rounded-xl px-4 outline-none" required/><button type="button" onClick={()=>setShow(!show)} className="px-4 text-sm font-semibold text-emerald-800">{show?"Hide":"Show"}</button></span></label>
    <div className="grid grid-cols-2 gap-3 text-sm"><Link href="/forgot-password" className="font-semibold text-emerald-800">Forgot Password?</Link><Link href="/therapist-activate" className="text-right font-semibold text-emerald-800">Activate Account</Link><Link href="/therapist-register" className="col-span-2 text-center font-semibold text-emerald-800">Register / Join JeevaSetu</Link></div>
    <button disabled={busy||mobile.length!==10||!password} className="button-primary w-full disabled:opacity-50">{busy?"Signing in…":"Login"}</button>
  </form>;
}

export function PractitionerActivation() {
  const [stage,setStage]=useState<"mobile"|"otp"|"password"|"done">("mobile");
  const [mobile,setMobile]=useState(""); const [verificationId,setVerificationId]=useState(""); const [token,setToken]=useState("");
  const [otp,setOtp]=useState(""); const [password,setPassword]=useState(""); const [confirm,setConfirm]=useState("");
  const [config,setConfig]=useState<OtpWidgetConfig>({enabled:false}); const [busy,setBusy]=useState(false); const [error,setError]=useState("");
  async function send(){if(!/^[6-9]\d{9}$/.test(mobile)){setError("Enter the 10-digit mobile number registered by JeevaSetu.");return;}setBusy(true);setError("");try{const widget=await loadOtpWidgetConfig();const issued=await requestJson<{verification_id:string}>("/api/booking-otp/issue",{method:"POST",body:JSON.stringify({mobile_number:mobile})});if(widget.enabled)await sendMsg91Otp(widget,mobile);setConfig(widget);setVerificationId(issued.verification_id);setStage("otp");}catch(value){setError(value instanceof Error?value.message:"OTP could not be sent.");}finally{setBusy(false)}}
  async function verify(){setBusy(true);setError("");try{const proof=config.enabled?{access_token:await verifyMsg91Otp(config,otp)}:{otp};const value=await requestJson<{token:string}>("/api/booking-otp/verify",{method:"POST",body:JSON.stringify({verification_id:verificationId,mobile_number:mobile,...proof})});setToken(value.token);setOtp("");setStage("password");}catch(value){setError(value instanceof Error?value.message:"Mobile verification failed.");}finally{setBusy(false)}}
  async function activate(event:React.FormEvent){event.preventDefault();if(!isStrongPassword(password)){setError("Password does not meet all requirements.");return;}if(password!==confirm){setError("Passwords do not match.");return;}setBusy(true);setError("");try{await requestJson("/api/session/practitioner-activate",{method:"POST",body:JSON.stringify({mobile_number:mobile,full_name:"Account Activation",booking_verification_token:token,password,confirm_password:confirm})});setStage("done");}catch(value){setError(value instanceof Error?value.message:"Account activation could not be completed.");}finally{setBusy(false)}}
  if(stage==="done")return <div className="space-y-5"><p role="status" className="rounded-xl bg-emerald-50 p-3 text-emerald-900">Activation successful. Your password is ready.</p><Link href="/therapist-login?activated=1" className="button-primary block text-center">Go to Therapist Login</Link></div>;
  return <div className="space-y-5">{error&&<p role="alert" className="rounded-xl bg-red-50 p-3 text-red-800">{error}</p>}{stage==="mobile"&&<><p className="text-sm text-slate-600">For therapists whose account was created by a JeevaSetu Owner. You will verify your registered mobile and choose your own password.</p><label className="grid gap-2 font-semibold">Registered mobile number<input className={fieldClass} inputMode="numeric" autoComplete="tel" maxLength={10} value={mobile} onChange={e=>setMobile(e.target.value.replace(/\D/g,""))}/></label><button onClick={send} disabled={busy||mobile.length!==10} className="button-primary w-full disabled:opacity-50">{busy?"Sending…":"Send OTP"}</button></>}{stage==="otp"&&<><label className="grid gap-2 font-semibold">One-time password<input aria-label="One-time password" className={`${fieldClass} tracking-[.35em]`} inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={otp} onChange={e=>setOtp(e.target.value.replace(/\D/g,""))}/></label><button onClick={verify} disabled={busy||otp.length!==6} className="button-primary w-full disabled:opacity-50">{busy?"Verifying…":"Verify Mobile"}</button><button onClick={send} disabled={busy} className="button-secondary w-full">Resend OTP</button></>}{stage==="password"&&<form onSubmit={activate} className="space-y-5"><p role="status" className="rounded-xl bg-emerald-50 p-3 text-emerald-900">Mobile number verified. Create a password known only to you.</p><PasswordCreationFields password={password} confirmPassword={confirm} onPasswordChange={setPassword} onConfirmPasswordChange={setConfirm} passwordLabel="Set Password" confirmLabel="Confirm Password"/><button disabled={busy||!isStrongPassword(password)||password!==confirm} className="button-primary w-full disabled:opacity-50">{busy?"Activating…":"Activate Account"}</button></form>}<Link href="/therapist-login" className="block text-center text-sm font-semibold text-emerald-800">Back to Therapist Login</Link></div>;
}

type Stage="details"|"otp"|"password";
export function PractitionerRegistration() {
  const router=useRouter();
  const [stage,setStage]=useState<Stage>("details");
  const [details,setDetails]=useState({full_name:"",mobile_number:"",email:""});
  const [verificationId,setVerificationId]=useState(""); const [token,setToken]=useState("");
  const [otp,setOtp]=useState(""); const [password,setPassword]=useState(""); const [confirm,setConfirm]=useState("");
  const [config,setConfig]=useState<OtpWidgetConfig>({enabled:false}); const [busy,setBusy]=useState(false); const [error,setError]=useState("");
  async function send(){if(details.full_name.trim().length<2||!/^[6-9]\d{9}$/.test(details.mobile_number)){setError("Enter your full name and a valid 10-digit Indian mobile number.");return;}setBusy(true);setError("");try{const widget=await loadOtpWidgetConfig();const issued=await requestJson<{verification_id:string}>("/api/booking-otp/issue",{method:"POST",body:JSON.stringify({mobile_number:details.mobile_number})});if(widget.enabled)await sendMsg91Otp(widget,details.mobile_number);setConfig(widget);setVerificationId(issued.verification_id);setStage("otp");}catch(value){setError(value instanceof Error?value.message:"OTP could not be sent.");}finally{setBusy(false)}}
  async function verify(){setBusy(true);setError("");try{const proof=config.enabled?{access_token:await verifyMsg91Otp(config,otp)}:{otp};const value=await requestJson<{token:string}>("/api/booking-otp/verify",{method:"POST",body:JSON.stringify({verification_id:verificationId,mobile_number:details.mobile_number,...proof})});setToken(value.token);setOtp("");setStage("password");}catch(value){setError(value instanceof Error?value.message:"Mobile verification failed.");}finally{setBusy(false)}}
  async function create(event:React.FormEvent){event.preventDefault();if(!isStrongPassword(password)){setError("Password does not meet all requirements.");return;}if(password!==confirm){setError("Passwords do not match.");return;}setBusy(true);setError("");try{await requestJson("/api/session/practitioner-register",{method:"POST",body:JSON.stringify({...details,booking_verification_token:token,password,confirm_password:confirm})});router.replace("/therapist-login?registered=1&returnTo=%2Fpractitioner-application");}catch(value){setError(value instanceof Error?value.message:"Practitioner account could not be created.");}finally{setBusy(false)}}
  return <div className="space-y-5"><ol className="grid grid-cols-3 gap-2 text-center text-xs font-bold"><li className={stage==="details"?"rounded-lg bg-emerald-700 p-2 text-white":"rounded-lg bg-emerald-50 p-2"}>1. Details</li><li className={stage==="otp"?"rounded-lg bg-emerald-700 p-2 text-white":"rounded-lg bg-slate-100 p-2"}>2. Verify Mobile</li><li className={stage==="password"?"rounded-lg bg-emerald-700 p-2 text-white":"rounded-lg bg-slate-100 p-2"}>3. Secure Account</li></ol>{error&&<p role="alert" className="rounded-xl bg-red-50 p-3 text-red-800">{error}</p>}{stage==="details"&&<><label className="grid gap-2 font-semibold">Full Name<input className={fieldClass} value={details.full_name} onChange={e=>setDetails({...details,full_name:e.target.value})}/></label><label className="grid gap-2 font-semibold">Mobile Number<input className={fieldClass} inputMode="numeric" maxLength={10} value={details.mobile_number} onChange={e=>setDetails({...details,mobile_number:e.target.value.replace(/\D/g,"")})}/></label><label className="grid gap-2 font-semibold">Email (optional)<input className={fieldClass} type="email" value={details.email} onChange={e=>setDetails({...details,email:e.target.value})}/></label><button onClick={send} disabled={busy} className="button-primary w-full">{busy?"Sending…":"Send OTP"}</button></>}{stage==="otp"&&<><p>Enter the OTP sent to your registered mobile.</p><input aria-label="One-time password" className={`${fieldClass} w-full tracking-[.35em]`} inputMode="numeric" maxLength={6} value={otp} onChange={e=>setOtp(e.target.value.replace(/\D/g,""))}/><button onClick={verify} disabled={busy||otp.length!==6} className="button-primary w-full disabled:opacity-50">{busy?"Verifying…":"Verify Mobile"}</button><button onClick={send} className="button-secondary w-full">Resend OTP</button></>}{stage==="password"&&<form onSubmit={create} className="space-y-5"><p role="status" className="rounded-xl bg-emerald-50 p-3 text-emerald-900">Mobile number verified</p><PasswordCreationFields password={password} confirmPassword={confirm} onPasswordChange={setPassword} onConfirmPasswordChange={setConfirm} passwordLabel="Password" confirmLabel="Confirm Password"/><button disabled={busy||!isStrongPassword(password)||password!==confirm} className="button-primary w-full">{busy?"Saving…":"Create / Activate Account"}</button></form>}<p className="text-center text-sm">Already registered? <Link href="/therapist-login" className="font-semibold text-emerald-800">Sign In</Link></p></div>;
}
