"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { ClientApiError, requestJson } from "@/lib/api/client";
import type { AppointmentRequest, TherapyOption } from "@/lib/appointments/contracts";
import { appointmentSchema, type AppointmentFormValues } from "@/lib/appointments/schema";
import type { PublicPractitioner } from "@/lib/practitioners/contracts";

const stepFields: Array<Array<keyof AppointmentFormValues>> = [
  ["patient_name", "age", "gender", "mobile_number", "alternate_mobile", "email"],
  ["therapy", "session_preference", "preferred_date", "preferred_time", "problem_description", "pain_area", "problem_duration", "doctor_reference", "preferred_practitioner"],
  ["address", "city", "pin_code", "landmark", "google_map_link"],
];

const labels: Record<keyof AppointmentFormValues, string> = {
  patient_name: "Patient name", age: "Age", gender: "Gender", mobile_number: "Mobile number", alternate_mobile: "Alternate mobile", email: "Email (optional)", therapy: "Therapy", preferred_practitioner: "Preferred practitioner (optional)", session_preference: "Session preference", preferred_date: "Preferred date", preferred_time: "Preferred time", problem_description: "Problem description", pain_area: "Pain area", problem_duration: "Duration of problem", doctor_reference: "Doctor reference (optional)", address: "Address", city: "City", pin_code: "PIN code", landmark: "Landmark", google_map_link: "Google Map link (optional)",
};

export function BookingForm() {
  const [step, setStep] = useState(0);
  const [submitted, setSubmitted] = useState<AppointmentRequest | null>(null);
  const { register, handleSubmit, getValues, setError, trigger, formState: { errors } } = useForm<AppointmentFormValues>({ defaultValues: { patient_name: "", age: 18, gender: "PREFER_NOT_TO_SAY", mobile_number: "", alternate_mobile: "", email: "", therapy: "", preferred_practitioner: "", session_preference: "SINGLE", preferred_date: "", preferred_time: "", problem_description: "", pain_area: "", problem_duration: "", doctor_reference: "", address: "", city: "Meerut", pin_code: "", landmark: "", google_map_link: "" } });
  const therapyQuery = useQuery({ queryKey: ["appointment-therapies"], queryFn: () => requestJson<TherapyOption[]>("/api/appointment-therapies") });
  const practitionerQuery = useQuery({ queryKey: ["public-practitioners"], queryFn: () => requestJson<PublicPractitioner[]>("/api/practitioners/public") });
  const submit = useMutation({ mutationFn: (values: AppointmentFormValues) => requestJson<AppointmentRequest>("/api/appointment-requests", { method: "POST", body: JSON.stringify(values) }), onSuccess: setSubmitted, onError: (error) => { if (error instanceof ClientApiError && error.fieldErrors) Object.entries(error.fieldErrors).forEach(([field, message]) => setError(field as keyof AppointmentFormValues, { message })); } });
  async function next() {
    const requiredValid = await trigger(stepFields[step]);
    let schemaValid = true;
    for (const name of stepFields[step]) {
      const result = appointmentSchema.shape[name].safeParse(getValues(name));
      if (!result.success) { schemaValid = false; setError(name, { message: result.error.issues[0]?.message }); }
    }
    if (requiredValid && schemaValid) setStep((value) => Math.min(3, value + 1));
  }
  function onSubmit(values: AppointmentFormValues) { const parsed = appointmentSchema.safeParse(values); if (!parsed.success) { parsed.error.issues.forEach((issue) => setError(issue.path[0] as keyof AppointmentFormValues, { message: issue.message })); setStep(0); return; } submit.mutate(parsed.data); }
  if (submitted) return <div className="card p-8 text-center" role="status"><p className="eyebrow">Request received</p><h2 className="mt-4 font-serif text-4xl text-[#103c27]">Thank you. We’ll review your request.</h2><p className="mt-4 text-[#5b6c63]">Reference: <strong>{submitted.id}</strong></p><p className="mt-2 text-[#5b6c63]">Current status: Pending. No payment or therapist assignment has been made.</p></div>;
  const field = (name: keyof AppointmentFormValues, type = "text") => <label className="grid gap-2 font-semibold text-[#163c2a]">{labels[name]}<input type={type} {...register(name, { required: !["alternate_mobile", "email", "doctor_reference", "google_map_link"].includes(name) })} className="min-h-12 rounded-xl border border-[#0b6b3a]/20 bg-white px-4 font-normal" aria-invalid={Boolean(errors[name])}/>{errors[name] && <span className="text-sm text-red-700">{errors[name]?.message ?? `${labels[name]} is required.`}</span>}</label>;
  return <form onSubmit={handleSubmit(onSubmit)} className="card p-5 sm:p-8" noValidate>
    <ol className="mb-8 grid grid-cols-4 gap-2" aria-label="Booking progress">{["Patient", "Service", "Location", "Confirm"].map((label, index) => <li key={label} className={`rounded-full px-2 py-2 text-center text-xs font-bold ${index === step ? "bg-[#0b6b3a] text-white" : "bg-[#edf7ef] text-[#0b6b3a]"}`}>{index + 1}. {label}</li>)}</ol>
    {step === 0 && <fieldset className="grid gap-5 sm:grid-cols-2"><legend className="mb-6 font-serif text-3xl text-[#103c27]">Patient information</legend>{field("patient_name")}{field("age", "number")}<label className="grid gap-2 font-semibold text-[#163c2a]">Gender<select {...register("gender")} className="min-h-12 rounded-xl border border-[#0b6b3a]/20 bg-white px-4 font-normal"><option value="FEMALE">Female</option><option value="MALE">Male</option><option value="OTHER">Other</option><option value="PREFER_NOT_TO_SAY">Prefer not to say</option></select></label>{field("mobile_number", "tel")}{field("alternate_mobile", "tel")}{field("email", "email")}</fieldset>}
    {step === 1 && <fieldset className="grid gap-5 sm:grid-cols-2"><legend className="mb-6 font-serif text-3xl text-[#103c27]">Service details</legend><label className="grid gap-2 font-semibold text-[#163c2a]">Therapy<select {...register("therapy", { required: true })} className="min-h-12 rounded-xl border border-[#0b6b3a]/20 bg-white px-4 font-normal"><option value="">Select a therapy</option>{therapyQuery.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>{therapyQuery.isError && <span className="text-sm text-red-700">Therapies are temporarily unavailable.</span>}</label><label className="grid gap-2 font-semibold text-[#163c2a]">Preferred practitioner<select {...register("preferred_practitioner")} className="min-h-12 rounded-xl border border-[#0b6b3a]/20 bg-white px-4 font-normal"><option value="">Assign the best available practitioner</option>{practitionerQuery.data?.map(item=><option key={item.id} value={item.id}>{item.display_name} · {item.highest_qualification}</option>)}</select><span className="text-xs font-normal text-[#68786f]">This is a preference only. JeevaSetu operations makes the final assignment.</span></label><label className="grid gap-2 font-semibold text-[#163c2a]">Session preference<select {...register("session_preference")} className="min-h-12 rounded-xl border border-[#0b6b3a]/20 bg-white px-4 font-normal"><option value="SINGLE">Single Session</option><option value="PACKAGE">Package</option></select></label>{field("preferred_date", "date")}{field("preferred_time", "time")}{field("pain_area")}{field("problem_duration")}<label className="grid gap-2 font-semibold text-[#163c2a] sm:col-span-2">Problem description<textarea {...register("problem_description", { required: true })} rows={5} className="rounded-xl border border-[#0b6b3a]/20 bg-white p-4 font-normal"/></label>{field("doctor_reference")}</fieldset>}
    {step === 2 && <fieldset className="grid gap-5 sm:grid-cols-2"><legend className="mb-6 font-serif text-3xl text-[#103c27]">Visit location</legend><div className="sm:col-span-2">{field("address")}</div>{field("city")}{field("pin_code")}{field("landmark")} {field("google_map_link", "url")}</fieldset>}
    {step === 3 && <section aria-labelledby="confirm-heading"><h2 id="confirm-heading" className="font-serif text-3xl text-[#103c27]">Confirm your request</h2><dl className="mt-6 grid gap-4 sm:grid-cols-2">{Object.entries(getValues()).filter(([, value]) => value).map(([key, value]) => <div key={key} className="rounded-xl bg-[#edf7ef] p-4"><dt className="text-xs font-bold uppercase text-[#0b6b3a]">{labels[key as keyof AppointmentFormValues]}</dt><dd className="mt-1 break-words text-[#163c2a]">{key === "therapy" ? therapyQuery.data?.find((item) => item.id === value)?.name : String(value)}</dd></div>)}</dl><button type="button" onClick={() => setStep(0)} className="button-secondary mt-6">Edit information</button>{submit.isError && <p className="mt-5 text-red-700" role="alert">{submit.error instanceof Error ? submit.error.message : "Request could not be submitted."}</p>}</section>}
    <div className="mt-8 flex justify-between gap-3">{step > 0 ? <button type="button" onClick={() => setStep((value) => value - 1)} className="button-secondary">Back</button> : <span/>}{step < 3 ? <button type="button" onClick={next} className="button-primary">Continue</button> : <button type="submit" disabled={submit.isPending} className="button-primary">{submit.isPending ? "Submitting…" : "Submit request"}</button>}</div>
  </form>;
}
