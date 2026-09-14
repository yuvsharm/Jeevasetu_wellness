"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { isStrongPassword, PasswordCreationFields } from "@/components/auth/password-creation-fields";
import { OtpInput, OtpResendButton } from "@/components/auth/otp-input";
import { AddressCapture } from "@/components/location/address-capture";
import { requestJson } from "@/lib/api/client";
import { loadOtpWidgetConfig, sendMsg91Otp, verifyMsg91Otp, type OtpWidgetConfig } from "@/lib/auth/msg91-widget";
import { emptyServiceAddress, isCompleteServiceAddress } from "@/lib/location/contracts";

type Details = {
  full_name: string; age: string; gender: string; mobile_number: string; email: string;
};
type Stage = "details" | "otp" | "secure";

const initial: Details = {
  full_name: "", age: "", gender: "", mobile_number: "", email: "",
};

function safeReturnTo(value: string | null) {
  return value?.startsWith("/") && !value.startsWith("//") ? value : "/customer";
}

export function CustomerRegistration() {
  const router = useRouter();
  const search = useSearchParams();
  const returnTo = safeReturnTo(search.get("returnTo"));
  const [details, setDetails] = useState(initial);
  const [address, setAddress] = useState({ ...emptyServiceAddress(), city: "Meerut", region: "Uttar Pradesh" });
  const [addressConfirmed, setAddressConfirmed] = useState(false);
  const [stage, setStage] = useState<Stage>("details");
  const [verificationId, setVerificationId] = useState("");
  const [verificationToken, setVerificationToken] = useState("");
  const [config, setConfig] = useState<OtpWidgetConfig>({ enabled: false });
  const [otp, setOtp] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [photo,setPhoto]=useState<File|null>(null);
  const [photoPreview,setPhotoPreview]=useState("");

  useEffect(()=>{
    if(!photo||typeof URL.createObjectURL!=="function"){setPhotoPreview("");return;}
    const value=URL.createObjectURL(photo);setPhotoPreview(value);
    return()=>URL.revokeObjectURL(value);
  },[photo]);

  function choosePhoto(file:File|null){
    if(!file){setPhoto(null);return;}
    if(!["image/jpeg","image/png","image/webp"].includes(file.type)){setError("Upload a JPG, PNG, or WebP photograph.");return;}
    if(file.size>2*1024*1024){setError("Profile photographs must not exceed 2 MB.");return;}
    setError("");setPhoto(file);
  }

  function invalidateVerification(nextStage: Stage = "details") {
    setVerificationId(""); setVerificationToken(""); setOtp(""); setPassword("");
    setConfirmPassword(""); setStage(nextStage);
  }

  function update(name: keyof Details, value: string) {
    setDetails((current) => ({ ...current, [name]: value }));
    if (name === "mobile_number" && (verificationId || verificationToken)) invalidateVerification();
  }

  function validateDetails() {
    if (details.full_name.trim().length < 2) return "Enter your full name.";
    if (!/^\d{1,3}$/.test(details.age) || Number(details.age) > 120) return "Enter a valid age.";
    if (!details.gender) return "Select your gender.";
    if (!/^[6-9]\d{9}$/.test(details.mobile_number)) return "Enter a valid 10-digit Indian mobile number.";
    if (!address.address_line_1.trim() || !address.city.trim() || !address.region.trim()) return "Enter your complete address.";
    if (!/^[1-9]\d{5}$/.test(address.pin_code.trim())) return "Enter a valid PIN code.";
    if (!isCompleteServiceAddress(address)) return "Enter your complete address.";
    if (!addressConfirmed) return "Review and confirm your service address.";
    if (Number(details.age) < 18) return "A parent or legal guardian must register and add a minor as a family member.";
    return "";
  }

  async function send() {
    const validation = validateDetails();
    if (validation) { setError(validation); return; }
    setBusy(true); setError(""); setVerificationToken("");
    try {
      const widget = await loadOtpWidgetConfig();
      const issued = await requestJson<{ verification_id: string }>("/api/booking-otp/issue", {
        method: "POST", body: JSON.stringify({ mobile_number: details.mobile_number }),
      });
      if (widget.enabled) await sendMsg91Otp(widget, details.mobile_number);
      setConfig(widget); setVerificationId(issued.verification_id); setOtp(""); setStage("otp");
    } catch (value) { setError(value instanceof Error ? value.message : "OTP could not be sent."); }
    finally { setBusy(false); }
  }

  async function verifyMobile() {
    if (!verificationId || otp.length !== 6) { setError("Enter the 6-digit OTP."); return; }
    setBusy(true); setError("");
    try {
      const providerProof = config.enabled ? { access_token: await verifyMsg91Otp(config, otp) } : { otp };
      const verified = await requestJson<{ token: string }>("/api/booking-otp/verify", {
        method: "POST", body: JSON.stringify({ verification_id: verificationId, mobile_number: details.mobile_number, ...providerProof }),
      });
      setVerificationToken(verified.token); setOtp(""); setStage("secure");
    } catch (value) { setError(value instanceof Error ? value.message : "Mobile verification could not be completed."); }
    finally { setBusy(false); }
  }

  async function createAccount(event: React.FormEvent) {
    event.preventDefault();
    if (!verificationToken) { setError("Please verify your mobile number again."); invalidateVerification(); return; }
    if (!isStrongPassword(password)) { setError("Password does not meet all requirements."); return; }
    if (password !== confirmPassword) { setError("Passwords do not match."); return; }
    setBusy(true); setError("");
    try {
      const payload={
        booking_verification_token: verificationToken, mobile_number: details.mobile_number,
        full_name: details.full_name, email: details.email, password, confirm_password: confirmPassword,
        age: Number(details.age), gender: details.gender,
        address,
      };
      const body=new FormData();body.append("payload",JSON.stringify(payload));if(photo)body.append("profile_photo",photo);
      await requestJson("/api/session/customer-register", {
        method: "POST",
        body,
      });
      setVerificationToken(""); setPassword(""); setConfirmPassword("");
      router.replace(`/customer-login?registered=1&returnTo=${encodeURIComponent(returnTo)}`);
      router.refresh();
    } catch (value) { setError(value instanceof Error ? value.message : "Customer registration could not be completed."); }
    finally { setBusy(false); }
  }

  const input = (name: keyof Details, label: string, options?: { type?: string; maxLength?: number }) => (
    <label className="grid gap-2 font-semibold text-slate-800">{label}<input type={options?.type ?? "text"} maxLength={options?.maxLength} value={details[name]} onChange={(event) => update(name, event.target.value)} className="min-h-12 rounded-xl border border-slate-300 px-4 font-normal" required={!label.includes("optional")} /></label>
  );

  return <div className="space-y-5">
    <ol aria-label="Registration progress" className="grid grid-cols-2 gap-2 text-center text-sm font-semibold">
      <li aria-current={stage !== "secure" ? "step" : undefined} className={`rounded-xl px-3 py-2 ${stage !== "secure" ? "bg-emerald-700 text-white" : "bg-emerald-50 text-emerald-800"}`}>1. Verify Mobile</li>
      <li aria-current={stage === "secure" ? "step" : undefined} className={`rounded-xl px-3 py-2 ${stage === "secure" ? "bg-emerald-700 text-white" : "bg-slate-100 text-slate-500"}`}>2. Secure Account</li>
    </ol>
    {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">{error}</p>}
    {stage === "details" && <>
      <div className="rounded-2xl border border-slate-200 p-4"><p className="font-semibold text-slate-800">Profile photo <span className="font-normal text-slate-500">(optional)</span></p><div className="mt-3 flex flex-wrap items-center gap-4">{photoPreview?<img src={photoPreview} alt="Selected profile preview" className="size-24 rounded-full object-cover"/>:<span className="flex size-24 items-center justify-center rounded-full bg-emerald-100 text-2xl font-bold text-emerald-800" aria-label="Profile initials">{details.full_name.trim().charAt(0).toUpperCase()||"C"}</span>}<div className="grid gap-2"><label className="button-secondary cursor-pointer">{photo?"Replace photo":"Choose photo"}<input aria-label="Profile photo" type="file" accept="image/jpeg,image/png,image/webp" className="sr-only !w-px !max-w-px" onChange={e=>choosePhoto(e.target.files?.[0]??null)}/></label>{photo&&<button type="button" className="text-left font-semibold text-red-700" onClick={()=>setPhoto(null)}>Remove selected photo</button>}<p className="text-xs text-slate-500">JPG, PNG or WebP, up to 2 MB. You can skip this.</p></div></div></div>
      {input("full_name", "Full name")}
      <div className="grid gap-5 sm:grid-cols-2">{input("age", "Age", { type: "number" })}<label className="grid gap-2 font-semibold text-slate-800">Gender<select value={details.gender} onChange={(event) => update("gender", event.target.value)} className="min-h-12 rounded-xl border border-slate-300 px-4 font-normal" required><option value="">Select gender</option><option value="FEMALE">Female</option><option value="MALE">Male</option><option value="OTHER">Other</option><option value="PREFER_NOT_TO_SAY">Prefer not to say</option></select></label></div>
      {input("mobile_number", "Mobile number", { type: "tel", maxLength: 10 })}{input("email", "Email (optional)", { type: "email" })}
      <AddressCapture
        value={address}
        onChange={(next) => { setAddress(next); setError(""); }}
        title="Service Address"
        initiallyExpanded={false}
        onConfirmedChange={(confirmed) => { setAddressConfirmed(confirmed); if (confirmed) setError(""); }}
      />
      <button type="button" disabled={busy} onClick={send} className="button-primary w-full disabled:opacity-50">{busy ? "Sending…" : "Send OTP"}</button>
    </>}
    {stage === "otp" && <>
      <p className="text-sm text-slate-600">Enter the OTP sent to your mobile number.</p>
      <OtpInput value={otp} onChange={setOtp} mobileNumber={details.mobile_number}/>
      <button type="button" disabled={busy || otp.length !== 6} onClick={verifyMobile} className="button-primary w-full disabled:opacity-50">{busy ? "Verifying…" : "Verify Mobile"}</button>
      <OtpResendButton busy={busy} onResend={send}/>
      <button type="button" onClick={() => invalidateVerification()} className="min-h-11 w-full font-semibold text-emerald-800">Edit details</button>
    </>}
    {stage === "secure" && <form className="space-y-5" onSubmit={createAccount}>
      <p role="status" className="rounded-xl bg-emerald-50 p-3 font-semibold text-emerald-900">Mobile number verified</p>
      <PasswordCreationFields password={password} confirmPassword={confirmPassword} onPasswordChange={setPassword} onConfirmPasswordChange={setConfirmPassword} />
      <button disabled={busy || !isStrongPassword(password) || password !== confirmPassword} className="button-primary w-full disabled:opacity-50">{busy ? "Creating account…" : "Create Account"}</button>
      <button type="button" disabled={busy} onClick={() => invalidateVerification()} className="min-h-11 w-full font-semibold text-emerald-800">Back to Step 1</button>
    </form>}
    <p className="text-center text-sm text-slate-600">Already registered? <Link className="font-semibold text-emerald-800" href={`/customer-login?returnTo=${encodeURIComponent(returnTo)}`}>Customer Login</Link></p>
  </div>;
}
