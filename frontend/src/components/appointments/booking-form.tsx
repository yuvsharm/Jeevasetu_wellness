"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { ClientApiError, requestJson } from "@/lib/api/client";
import type { AppointmentRequest, TherapyOption } from "@/lib/appointments/contracts";
import type { AppointmentFormValues } from "@/lib/appointments/schema";
import type { PublicPractitioner } from "@/lib/practitioners/contracts";

const labels: Record<keyof AppointmentFormValues, string> = {
  patient_name: "Patient name",
  age: "Age",
  gender: "Gender",
  mobile_number: "Mobile number",
  alternate_mobile: "Alternate mobile",
  email: "Email (optional)",
  therapy: "Therapy",
  requested_therapies: "Preferred therapies",
  preferred_practitioner: "Preferred practitioner (optional)",
  session_preference: "Session preference",
  preferred_date: "Preferred date",
  preferred_time: "Preferred time",
  problem_description: "Problem description",
  pain_area: "Pain area",
  problem_duration: "Duration of problem",
  doctor_reference: "Doctor reference (optional)",
  address: "Address",
  city: "City",
  pin_code: "PIN code",
  landmark: "Landmark",
  google_map_link: "Google Map link (optional)",
};

const getDefaults = (initialTherapy = "") => ({
  patient_name: "",
  age: 18,
  gender: "PREFER_NOT_TO_SAY" as const,
  mobile_number: "",
  alternate_mobile: "",
  email: "",
  therapy: initialTherapy,
  preferred_practitioner: "",
  session_preference: "SINGLE" as const,
  preferred_date: "",
  preferred_time: "",
  problem_description: "",
  pain_area: "",
  problem_duration: "",
  doctor_reference: "",
  address: "",
  city: "Meerut",
  pin_code: "",
  landmark: "",
  google_map_link: "",
});

export function BookingForm({ initialTherapy = "", quickMode = false }: { initialTherapy?: string; quickMode?: boolean }) {
  const [step, setStep] = useState(0);
  const [submitted, setSubmitted] = useState<AppointmentRequest | null>(null);
  const [otpSent, setOtpSent] = useState(false);
  const [otpVerified, setOtpVerified] = useState(false);
  const [otpCode, setOtpCode] = useState("");
  const [otpError, setOtpError] = useState("");
  const [selectedTherapies, setSelectedTherapies] = useState<string[]>(initialTherapy ? [initialTherapy] : []);

  const form = useForm<AppointmentFormValues>({ defaultValues: getDefaults(initialTherapy) });
  const therapyQuery = useQuery({ queryKey: ["appointment-therapies"], queryFn: () => requestJson<TherapyOption[]>("/api/appointment-therapies") });
  const practitionerQuery = useQuery({ queryKey: ["public-practitioners"], queryFn: () => requestJson<PublicPractitioner[]>("/api/practitioners/public") });

  const submit = useMutation({
    mutationFn: (values: AppointmentFormValues) => requestJson<AppointmentRequest>("/api/appointment-requests", { method: "POST", body: JSON.stringify(values) }),
    onSuccess: setSubmitted,
    onError: (error) => {
      if (error instanceof ClientApiError && error.fieldErrors) {
        Object.entries(error.fieldErrors).forEach(([field, message]) => form.setError(field as keyof AppointmentFormValues, { message }));
      }
    },
  });

  const next = async () => {
    if (step === 0) {
      const valid = await form.trigger(["patient_name", "age", "gender", "mobile_number", "email"]);
      if (!valid) return;
    }
    if (step === 1) {
      const valid = await form.trigger(["therapy", "session_preference", "preferred_date", "preferred_time", "problem_description", "pain_area", "problem_duration"]);
      if (!valid) return;
    }
    if (step === 2) {
      const valid = await form.trigger(["address", "city", "pin_code", "landmark"]);
      if (!valid) return;
    }
    setStep((value) => Math.min(value + 1, 3));
  };

  const onSubmit = form.handleSubmit((values) => {
    submit.mutate(values);
  });

  if (submitted) {
    return (
      <div className="card p-8 text-center" role="status">
        <p className="eyebrow">Request received</p>
        <h2 className="mt-4 font-serif text-4xl text-[#103c27]">Thank you. We’ll review your request.</h2>
        <p className="mt-4 text-[#5b6c63]">Reference: <strong>{submitted.id}</strong></p>
        <p className="mt-2 text-[#5b6c63]">Current status: Pending. No payment or therapist assignment has been made.</p>
      </div>
    );
  }

  const field = (name: keyof AppointmentFormValues, type = "text") => (
    <label className="grid gap-2 font-semibold text-[#163c2a]">
      {labels[name]}
      <input
        type={type}
        {...form.register(name, { required: !["alternate_mobile", "email", "doctor_reference", "google_map_link", "requested_therapies"].includes(name) })}
        className="min-h-12 rounded-xl border border-[#0b6b3a]/20 bg-white px-4 font-normal"
        aria-invalid={Boolean(form.formState.errors[name])}
      />
      {form.formState.errors[name] && (
        <span className="text-sm text-red-700">{form.formState.errors[name]?.message ?? `${labels[name]} is required.`}</span>
      )}
    </label>
  );

  if (quickMode) {
    const therapyOptions = therapyQuery.data ?? [];
    const primaryTherapyId = initialTherapy || selectedTherapies[0] || therapyOptions[0]?.id || "";

    const handleSubmitQuick = () => {
      const mobile_number = form.getValues("mobile_number");
      if (!/^[6-9]\d{9}$/.test(mobile_number)) {
        setOtpError("Enter a valid 10-digit Indian mobile number.");
        return;
      }
      if (!otpVerified) {
        setOtpError("Please verify your mobile number before submitting the request.");
        return;
      }
      if (!selectedTherapies.length) {
        setOtpError("Select at least one therapy to continue.");
        return;
      }
      if (!form.getValues("preferred_date") || !form.getValues("preferred_time")) {
        setOtpError("Choose a preferred date and time before submitting.");
        return;
      }

      const payload = {
        ...getDefaults(primaryTherapyId),
        ...form.getValues(),
        patient_name: "Quick Appointment Guest",
        age: 30,
        gender: "PREFER_NOT_TO_SAY",
        mobile_number,
        therapy: primaryTherapyId,
        session_preference: "SINGLE",
        preferred_practitioner: "",
        problem_description: form.getValues("problem_description") || "Quick appointment request from public booking flow.",
        pain_area: form.getValues("pain_area") || "General wellness consultation",
        problem_duration: form.getValues("problem_duration") || "Not specified",
        address: form.getValues("address") || "Meerut",
        city: form.getValues("city") || "Meerut",
        pin_code: form.getValues("pin_code") || "250001",
        landmark: form.getValues("landmark") || "Near local landmark",
        google_map_link: form.getValues("google_map_link") || "",
        requested_therapies: selectedTherapies,
      } as AppointmentFormValues & { requested_therapies?: string[] };

      submit.mutate(payload as AppointmentFormValues);
    };

    return (
      <form className="card p-5 sm:p-8" noValidate onSubmit={(event) => { event.preventDefault(); handleSubmitQuick(); }}>
        <div className="mb-8 flex items-start justify-between gap-4">
          <div>
            <h2 className="font-serif text-3xl text-[#103c27]">Quick Appointment</h2>
            <p className="mt-3 text-[#5b6c63]">Verify your mobile and choose the service.</p>
          </div>
          <span className="rounded-full bg-[#edf7ef] px-3 py-1 text-xs font-bold uppercase tracking-[0.16em] text-[#0b6b3a]">1-minute request</span>
        </div>

        <div className="grid gap-5 sm:grid-cols-[minmax(0,1fr)_auto]">
          <label className="grid gap-2 font-semibold text-[#163c2a]">
            Mobile number
            <input
              type="tel"
              value={form.watch("mobile_number")}
              onChange={(event) => {
                const cleaned = event.target.value.replace(/\D/g, "").slice(0, 10);
                form.setValue("mobile_number", cleaned, { shouldValidate: true });
                setOtpSent(false);
                setOtpVerified(false);
                setOtpCode("");
                setOtpError("");
              }}
              className="min-h-12 rounded-xl border border-[#0b6b3a]/20 bg-white px-4 font-normal"
              placeholder="9876543210"
            />
          </label>
          <button type="button" onClick={() => {
            const mobile_number = form.getValues("mobile_number");
            if (!/^[6-9]\d{9}$/.test(mobile_number)) {
              setOtpError("Enter a valid 10-digit Indian mobile number.");
              return;
            }
            setOtpError("");
            setOtpSent(true);
          }} className="button-secondary self-end">{otpSent ? "Resend OTP" : "Send OTP"}</button>
        </div>

        {otpError && <p className="mt-3 text-sm text-red-700" role="alert">{otpError}</p>}

        {otpSent && (
          <div className="mt-5 grid gap-5 sm:grid-cols-[minmax(0,1fr)_auto]">
            <label className="grid gap-2 font-semibold text-[#163c2a]">
              Enter OTP
              <input
                type="text"
                inputMode="numeric"
                pattern="\\d{6}"
                maxLength={6}
                value={otpCode}
                onChange={(event) => setOtpCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                className="min-h-12 rounded-xl border border-[#0b6b3a]/20 bg-white px-4 font-mono text-lg tracking-[0.3em]"
                placeholder="123456"
              />
            </label>
            <button type="button" onClick={() => {
              if (otpCode.length !== 6) {
                setOtpError("Enter the 6-digit OTP sent to your mobile number.");
                return;
              }
              setOtpVerified(true);
              setOtpError("");
            }} className="button-primary self-end">Verify OTP</button>
          </div>
        )}

        {otpVerified && (
          <div className="mt-5 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800">
            Mobile verified. Your visit request can now be submitted.
          </div>
        )}

        <div className="mt-8 grid gap-5 sm:grid-cols-2">
          <label className="grid gap-2 font-semibold text-[#163c2a]">
            Preferred date
            <input type="date" {...form.register("preferred_date")} className="min-h-12 rounded-xl border border-[#0b6b3a]/20 bg-white px-4 font-normal" />
          </label>
          <label className="grid gap-2 font-semibold text-[#163c2a]">
            Preferred time
            <input type="time" {...form.register("preferred_time")} className="min-h-12 rounded-xl border border-[#0b6b3a]/20 bg-white px-4 font-normal" />
          </label>
        </div>

        <div className="mt-8">
          <p className="mb-4 font-semibold text-[#163c2a]">Preferred therapies</p>
          <div className="grid gap-3 sm:grid-cols-2">
            {therapyOptions.map((item) => {
              const isSelected = selectedTherapies.includes(item.id);
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    setSelectedTherapies((current) => current.includes(item.id) ? current.filter((value) => value !== item.id) : [...current, item.id]);
                  }}
                  className={`rounded-2xl border px-4 py-3 text-left transition ${isSelected ? "border-[#0b6b3a] bg-[#edf7ef] text-[#103c27]" : "border-[#d7e3dc] bg-white text-[#163c2a]"}`}
                >
                  <span className="flex items-center justify-between gap-3">
                    <span className="font-semibold">{item.name}</span>
                    <span className={`inline-flex h-6 w-6 items-center justify-center rounded-full border text-xs ${isSelected ? "border-[#0b6b3a] bg-[#0b6b3a] text-white" : "border-[#8ca99d] text-[#0b6b3a]"}`} aria-hidden="true">{isSelected ? "✓" : "+"}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="mt-8 flex justify-end">
          <button type="submit" disabled={submit.isPending || !otpVerified} className="button-primary disabled:cursor-not-allowed disabled:opacity-50">
            {submit.isPending ? "Submitting…" : "Submit request"}
          </button>
        </div>

        {submit.isError && <p className="mt-5 text-red-700" role="alert">{submit.error instanceof Error ? submit.error.message : "Request could not be submitted."}</p>}
      </form>
    );
  }

  return (
    <form onSubmit={onSubmit} className="card p-5 sm:p-8" noValidate>
      <ol className="mb-8 grid grid-cols-4 gap-2" aria-label="Booking progress">{["Patient", "Service", "Location", "Confirm"].map((label, index) => <li key={label} className={`rounded-full px-2 py-2 text-center text-xs font-bold ${index === step ? "bg-[#0b6b3a] text-white" : "bg-[#edf7ef] text-[#0b6b3a]"}`}>{index + 1}. {label}</li>)}</ol>
      {step === 0 && <fieldset className="grid gap-5 sm:grid-cols-2"><legend className="mb-6 font-serif text-3xl text-[#103c27]">Patient information</legend>{field("patient_name")}{field("age", "number")}<label className="grid gap-2 font-semibold text-[#163c2a]">Gender<select {...form.register("gender")} className="min-h-12 rounded-xl border border-[#0b6b3a]/20 bg-white px-4 font-normal"><option value="FEMALE">Female</option><option value="MALE">Male</option><option value="OTHER">Other</option><option value="PREFER_NOT_TO_SAY">Prefer not to say</option></select></label>{field("mobile_number", "tel")}{field("alternate_mobile", "tel")}{field("email", "email")}</fieldset>}
      {step === 1 && <fieldset className="grid gap-5 sm:grid-cols-2"><legend className="mb-6 font-serif text-3xl text-[#103c27]">Service details</legend><label className="grid gap-2 font-semibold text-[#163c2a]">Therapy<select {...form.register("therapy", { required: true })} className="min-h-12 rounded-xl border border-[#0b6b3a]/20 bg-white px-4 font-normal"><option value="">Select a therapy</option>{therapyQuery.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>{therapyQuery.isError && <span className="text-sm text-red-700">Therapies are temporarily unavailable.</span>}</label><label className="grid gap-2 font-semibold text-[#163c2a]">Preferred practitioner<select {...form.register("preferred_practitioner")} className="min-h-12 rounded-xl border border-[#0b6b3a]/20 bg-white px-4 font-normal"><option value="">Assign the best available practitioner</option>{practitionerQuery.data?.map((item) => <option key={item.id} value={item.id}>{item.display_name} · {item.highest_qualification}</option>)}</select><span className="text-xs font-normal text-[#68786f]">This is a preference only. JeevaSetu operations makes the final assignment.</span></label><label className="grid gap-2 font-semibold text-[#163c2a]">Session preference<select {...form.register("session_preference")} className="min-h-12 rounded-xl border border-[#0b6b3a]/20 bg-white px-4 font-normal"><option value="SINGLE">Single Session</option><option value="PACKAGE">Package</option></select></label>{field("preferred_date", "date")}{field("preferred_time", "time")}{field("pain_area")}{field("problem_duration")}<label className="grid gap-2 font-semibold text-[#163c2a] sm:col-span-2">Problem description<textarea {...form.register("problem_description", { required: true })} rows={5} className="rounded-xl border border-[#0b6b3a]/20 bg-white p-4 font-normal" /></label>{field("doctor_reference")}</fieldset>}
      {step === 2 && <fieldset className="grid gap-5 sm:grid-cols-2"><legend className="mb-6 font-serif text-3xl text-[#103c27]">Visit location</legend><div className="sm:col-span-2">{field("address")}</div>{field("city")}{field("pin_code")}{field("landmark")} {field("google_map_link", "url")}</fieldset>}
      {step === 3 && <section aria-labelledby="confirm-heading"><h2 id="confirm-heading" className="font-serif text-3xl text-[#103c27]">Confirm your request</h2><dl className="mt-6 grid gap-4 sm:grid-cols-2">{Object.entries(form.getValues()).filter(([, value]) => value).map(([key, value]) => <div key={key} className="rounded-xl bg-[#edf7ef] p-4"><dt className="text-xs font-bold uppercase text-[#0b6b3a]">{labels[key as keyof AppointmentFormValues]}</dt><dd className="mt-1 break-words text-[#163c2a]">{key === "therapy" ? therapyQuery.data?.find((item) => item.id === value)?.name : String(value)}</dd></div>)}</dl><button type="button" onClick={() => setStep(0)} className="button-secondary mt-6">Edit information</button>{submit.isError && <p className="mt-5 text-red-700" role="alert">{submit.error instanceof Error ? submit.error.message : "Request could not be submitted."}</p>}</section>}
      <div className="mt-8 flex justify-between gap-3">{step > 0 ? <button type="button" onClick={() => setStep((value) => value - 1)} className="button-secondary">Back</button> : <span />}{step < 3 ? <button type="button" onClick={next} className="button-primary">Continue</button> : <button type="submit" onClick={(e) => { e.preventDefault(); onSubmit(); }} disabled={submit.isPending} className="button-primary">{submit.isPending ? "Submitting…" : "Submit request"}</button>}</div>
    </form>
  );
}
