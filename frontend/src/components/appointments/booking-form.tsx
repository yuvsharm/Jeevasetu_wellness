"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useSession } from "@/components/auth/session-provider";
import { ClientApiError, requestJson } from "@/lib/api/client";
import type { AppointmentRequest, CommercialCatalog, CommercialQuote } from "@/lib/appointments/contracts";
import { activeRoles } from "@/lib/auth/roles";

type FamilyMember = { id: string; full_name: string; age: number; gender: string; relationship: string };
type AvailableSlot = { value: string; label: string };

export function BookingForm({ initialTherapy = "", initialPackage = "", initialOffer = "" }: {
  initialTherapy?: string;
  initialPackage?: string;
  initialOffer?: string;
}) {
  const session = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const queryClient = useQueryClient();
  const roles = session.data ? activeRoles(session.data.access.roles) : [];
  const customer = roles.includes("CUSTOMER");
  const [selectedTherapies, setSelectedTherapies] = useState<string[] | null>(initialTherapy ? [initialTherapy] : null);
  const [familyMember, setFamilyMember] = useState("");
  const [preferredDate, setPreferredDate] = useState("");
  const [preferredTime, setPreferredTime] = useState("");
  const [painArea, setPainArea] = useState("");
  const [addingFamily, setAddingFamily] = useState(false);
  const [familyDraft, setFamilyDraft] = useState({ full_name: "", age: "", gender: "", relationship: "" });
  const [submitted, setSubmitted] = useState<AppointmentRequest | null>(null);

  const intended = `${pathname}${search.toString() ? `?${search.toString()}` : ""}`;
  useEffect(() => {
    if (session.isPending) return;
    if (!session.data) router.replace(`/customer-access?returnTo=${encodeURIComponent(intended)}`);
    else if (!customer) router.replace("/unauthorized");
  }, [customer, intended, router, session.data, session.isPending]);

  const catalogQuery = useQuery({
    queryKey: ["commercial-public"],
    queryFn: () => requestJson<CommercialCatalog>("/api/commercial/public"),
    enabled: customer,
  });
  const familyQuery = useQuery({
    queryKey: ["customer-family"],
    queryFn: () => requestJson<FamilyMember[]>("/api/customer/family"),
    enabled: customer,
  });
  const catalog = catalogQuery.data;

  const effectiveTherapies = useMemo(() => {
    if (selectedTherapies) return selectedTherapies;
    const packageTherapy = catalog?.packages.find((value) => value.id === initialPackage)?.therapy;
    const offerTherapies = catalog?.offers.find((value) => value.id === initialOffer)?.eligible_therapies;
    if (packageTherapy) return [packageTherapy];
    return offerTherapies ?? [];
  }, [catalog, initialOffer, initialPackage, selectedTherapies]);

  const quoteQuery = useQuery({
    queryKey: ["commercial-quote", effectiveTherapies, initialPackage, initialOffer, familyMember, preferredDate, preferredTime],
    enabled: customer && effectiveTherapies.length > 0,
    queryFn: () => requestJson<CommercialQuote>("/api/commercial/quote", {
      method: "POST",
      body: JSON.stringify({
        therapy_ids: effectiveTherapies,
        package_id: initialPackage || null,
        offer_id: initialOffer || null,
        family_member_id: familyMember || null,
        service_at: preferredDate
          ? new Date(`${preferredDate}T${preferredTime || "12:00"}:00+05:30`).toISOString()
          : null,
      }),
    }),
  });
  const slotsQuery = useQuery({
    queryKey: ["customer-slots", effectiveTherapies, initialPackage, initialOffer, preferredDate],
    enabled: customer && Boolean(effectiveTherapies[0]) && Boolean(preferredDate),
    queryFn: () => {
      const query = new URLSearchParams({ therapy: effectiveTherapies[0], date: preferredDate });
      if (effectiveTherapies.length > 1) query.set("requested_therapies", effectiveTherapies.slice(1).join(","));
      if (initialPackage) query.set("package", initialPackage);
      if (initialOffer) query.set("offer", initialOffer);
      return requestJson<AvailableSlot[]>(`/api/availability/customer-slots?${query}`);
    },
  });

  const createFamily = useMutation({
    mutationFn: () => requestJson<FamilyMember>("/api/customer/family", {
      method: "POST",
      body: JSON.stringify({ ...familyDraft, age: Number(familyDraft.age), relevant_details: "" }),
    }),
    onSuccess: async (value) => {
      await queryClient.invalidateQueries({ queryKey: ["customer-family"] });
      setFamilyMember(value.id);
      setAddingFamily(false);
    },
  });

  const submit = useMutation({
    mutationFn: () => requestJson<AppointmentRequest>("/api/appointment-requests", {
      method: "POST",
      body: JSON.stringify({
        therapy: effectiveTherapies[0],
        requested_therapies: effectiveTherapies.slice(1),
        family_member: familyMember || null,
        selected_package: initialPackage || null,
        selected_offer: initialOffer || null,
        preferred_date: preferredDate,
        preferred_time: preferredTime,
        pain_area: painArea.trim(),
      }),
    }),
    onSuccess: setSubmitted,
  });

  const selectedNames = useMemo(() => (catalog?.therapies ?? []).filter((value) => effectiveTherapies.includes(value.id)).map((value) => value.name), [catalog, effectiveTherapies]);

  if (session.isPending || !customer) return <div className="card p-8 text-center text-slate-600">Confirming customer access…</div>;
  if (submitted) return <div className="card p-8 text-center" role="status"><p className="eyebrow">Request received</p><h2 className="mt-4 font-serif text-4xl text-[#103c27]">Booking request submitted successfully.</h2><dl className="mx-auto mt-5 grid max-w-sm gap-2 text-left"><div className="flex justify-between gap-4"><dt>Requested Date</dt><dd className="font-semibold">{submitted.preferred_date}</dd></div><div className="flex justify-between gap-4"><dt>Requested Time</dt><dd className="font-semibold">{submitted.preferred_time}</dd></div><div className="flex justify-between gap-4"><dt>Status</dt><dd className="font-semibold">Awaiting confirmation</dd></div></dl><p className="mt-4 text-[#5b6c63]">Reference: <strong>{submitted.id}</strong></p></div>;

  const error = submit.error instanceof Error ? submit.error.message : "";
  return <form className="card space-y-7 p-5 sm:p-8" onSubmit={(event) => { event.preventDefault(); submit.mutate(); }}>
    <div><p className="eyebrow">Authenticated booking</p><h2 className="mt-2 font-serif text-3xl text-[#103c27]">Choose care and a preferred slot</h2><p className="mt-2 text-sm text-[#5b6c63]">Your verified profile and primary service address will be used automatically.</p></div>

    <fieldset><legend className="font-semibold text-[#163c2a]">Therapy / therapies</legend><div className="mt-3 grid gap-3 sm:grid-cols-2">{catalog?.therapies.map((therapy) => { const selected = effectiveTherapies.includes(therapy.id); return <button type="button" key={therapy.id} aria-pressed={selected} onClick={() => setSelectedTherapies(selected ? effectiveTherapies.filter((value) => value !== therapy.id) : [...effectiveTherapies, therapy.id])} className={`rounded-xl border p-4 text-left ${selected ? "border-emerald-700 bg-emerald-50" : "border-slate-200"}`}><span className="font-semibold">{therapy.name}</span><span className="mt-1 block text-sm text-slate-600">₹{Number(therapy.base_price ?? 0).toLocaleString("en-IN")}</span></button>; })}</div></fieldset>

    <label className="grid gap-2 font-semibold text-[#163c2a]">Booking for<select value={familyMember} onChange={(event) => setFamilyMember(event.target.value)} className="min-h-12 rounded-xl border border-slate-300 px-4 font-normal"><option value="">Myself</option>{familyQuery.data?.map((member) => <option key={member.id} value={member.id}>{member.full_name} ({member.relationship})</option>)}</select></label>
    <button type="button" className="text-left text-sm font-semibold text-emerald-800 underline" onClick={() => setAddingFamily((value) => !value)}>Add another patient</button>
    {addingFamily && <div className="grid gap-4 rounded-xl bg-emerald-50 p-4 sm:grid-cols-2">
      <label className="grid gap-1 text-sm font-semibold">Full name<input className="min-h-11 rounded-lg border px-3" value={familyDraft.full_name} onChange={(event) => setFamilyDraft({ ...familyDraft, full_name: event.target.value })} /></label>
      <label className="grid gap-1 text-sm font-semibold">Relationship<input className="min-h-11 rounded-lg border px-3" value={familyDraft.relationship} onChange={(event) => setFamilyDraft({ ...familyDraft, relationship: event.target.value })} /></label>
      <label className="grid gap-1 text-sm font-semibold">Age<input type="number" className="min-h-11 rounded-lg border px-3" value={familyDraft.age} onChange={(event) => setFamilyDraft({ ...familyDraft, age: event.target.value })} /></label>
      <label className="grid gap-1 text-sm font-semibold">Gender<select className="min-h-11 rounded-lg border px-3" value={familyDraft.gender} onChange={(event) => setFamilyDraft({ ...familyDraft, gender: event.target.value })}><option value="">Select</option><option value="FEMALE">Female</option><option value="MALE">Male</option><option value="OTHER">Other</option><option value="PREFER_NOT_TO_SAY">Prefer not to say</option></select></label>
      <button type="button" disabled={createFamily.isPending} onClick={() => createFamily.mutate()} className="button-secondary sm:col-span-2">{createFamily.isPending ? "Adding…" : "Add patient"}</button>
    </div>}

    <div className="grid gap-5 sm:grid-cols-2"><label className="grid gap-2 font-semibold text-[#163c2a]">Date<input type="date" required value={preferredDate} onChange={(event) => { setPreferredDate(event.target.value); setPreferredTime(""); }} className="min-h-12 rounded-xl border border-slate-300 px-4 font-normal" /></label><label className="grid gap-2 font-semibold text-[#163c2a]">Available time slot<select required disabled={!preferredDate || slotsQuery.isPending || slotsQuery.isError} value={preferredTime} onChange={(event) => setPreferredTime(event.target.value)} className="min-h-12 rounded-xl border border-slate-300 px-4 font-normal"><option value="">{slotsQuery.isPending ? "Loading available slots…" : "Select a time"}</option>{slotsQuery.data?.map((slot) => <option key={slot.value} value={slot.value}>{slot.label}</option>)}</select></label></div>
    {preferredDate && slotsQuery.data?.length === 0 && <p role="status" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">No appointment slots are available for this date.</p>}
    {slotsQuery.isError && <p role="alert" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">{slotsQuery.error.message}</p>}
    <label className="grid gap-2 font-semibold text-[#163c2a]">Pain area (optional)<input value={painArea} maxLength={160} onChange={(event) => setPainArea(event.target.value)} className="min-h-12 rounded-xl border border-slate-300 px-4 font-normal" /></label>

    {quoteQuery.data && <div className="rounded-xl bg-[#f7f3e9] p-4"><p className="font-semibold text-[#163c2a]">{selectedNames.join(" + ")}</p><p className="mt-2 text-sm">Duration: {quoteQuery.data.duration_minutes} minutes</p><p className="mt-1 text-xl font-bold text-emerald-800">₹{Number(quoteQuery.data.final_amount).toLocaleString("en-IN")}</p>{Number(quoteQuery.data.discount_amount) > 0 && <p className="text-sm text-slate-600">You save ₹{Number(quoteQuery.data.discount_amount).toLocaleString("en-IN")}</p>}</div>}
    {(error || createFamily.error) && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">{error || (createFamily.error instanceof Error ? createFamily.error.message : "The patient could not be added.")}</p>}
    <button disabled={submit.isPending || !effectiveTherapies.length || !preferredDate || !preferredTime || quoteQuery.isPending} className="button-primary w-full disabled:opacity-50">{submit.isPending ? "Booking…" : "Confirm Book Appointment"}</button>
    {submit.error instanceof ClientApiError && submit.error.fieldErrors && <ul className="text-sm text-red-700">{Object.values(submit.error.fieldErrors).map((value) => <li key={value}>{value}</li>)}</ul>}
  </form>;
}
