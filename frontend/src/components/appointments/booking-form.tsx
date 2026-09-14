"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useSession } from "@/components/auth/session-provider";
import { AddressCapture } from "@/components/location/address-capture";
import { ClientApiError, requestJson } from "@/lib/api/client";
import type { AppointmentRequest, CommercialCatalog, CommercialQuote } from "@/lib/appointments/contracts";
import { activeRoles } from "@/lib/auth/roles";
import { emptyServiceAddress, type ServiceAddress } from "@/lib/location/contracts";

type FamilyMember = { id: string; full_name: string; age: number; gender: string; relationship: string };
type AvailableSlot = { value: string; label: string };
const CLINIC_TIME_ZONE = "Asia/Kolkata";
const localDate = (value: Date | string) => new Intl.DateTimeFormat("en-CA", {
  timeZone: CLINIC_TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit",
}).format(new Date(value));
const inclusiveOfferEndDate = (value: string) => localDate(new Date(new Date(value).getTime() - 1));

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
  const [differentAddress, setDifferentAddress] = useState(false);
  const [serviceAddress, setServiceAddress] = useState<ServiceAddress>(emptyServiceAddress());
  const [savePrimaryAddress, setSavePrimaryAddress] = useState(false);
  const [serviceAddressConfirmed, setServiceAddressConfirmed] = useState(false);

  const intended = `${pathname}${search.toString() ? `?${search.toString()}` : ""}`;
  useEffect(() => {
    if (session.isPending) return;
    if (!session.data && session.error instanceof ClientApiError && session.error.status === 401) {
      router.replace(`/customer-login?reason=expired&returnTo=${encodeURIComponent(intended)}`);
    } else if (!session.data) router.replace(`/customer-access?returnTo=${encodeURIComponent(intended)}`);
    else if (!customer) router.replace("/unauthorized");
  }, [customer, intended, router, session.data, session.error, session.isPending]);

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
  const profileQuery = useQuery({
    queryKey: ["customer-profile"],
    queryFn: () => requestJson<{address:ServiceAddress|null}>("/api/customer/profile"),
    enabled: customer,
  });
  const catalog = catalogQuery.data;
  const selectedOffer = catalog?.offers.find((value) => value.id === initialOffer);
  const offerUnavailable = Boolean(initialOffer && catalogQuery.isSuccess && !selectedOffer);
  const normalMinDate = localDate(new Date());
  const minDate = selectedOffer?.valid_from
    ? [normalMinDate, localDate(selectedOffer.valid_from)].sort().at(-1)!
    : normalMinDate;
  const maxDate = selectedOffer?.valid_until ? inclusiveOfferEndDate(selectedOffer.valid_until) : undefined;
  const dateOutsideOfferWindow = Boolean(
    selectedOffer && preferredDate && (preferredDate < minDate || (maxDate && preferredDate > maxDate)),
  );

  const effectiveTherapies = useMemo(() => {
    if (selectedTherapies) return selectedTherapies;
    const packageTherapy = catalog?.packages.find((value) => value.id === initialPackage)?.therapy;
    const offer = catalog?.offers.find((value) => value.id === initialOffer);
    if (packageTherapy) return [packageTherapy];
    if (!offer) return [];
    if (offer.offer_type === "FIXED_BUNDLE") return offer.eligible_therapies;
    return offer.eligible_therapies.slice(0, Math.max(1, offer.minimum_therapy_count));
  }, [catalog, initialOffer, initialPackage, selectedTherapies]);
  const eligibleSelectedCount = selectedOffer
    ? effectiveTherapies.filter((id) => selectedOffer.eligible_therapies.includes(id)).length
    : effectiveTherapies.length;
  const remainingTherapies = selectedOffer
    ? Math.max(0, selectedOffer.minimum_therapy_count - eligibleSelectedCount)
    : 0;
  const offerUnlocked = !selectedOffer || remainingTherapies === 0;

  const quoteQuery = useQuery({
    queryKey: ["commercial-quote", effectiveTherapies, initialPackage, initialOffer, familyMember, preferredDate, preferredTime],
    enabled: customer && effectiveTherapies.length > 0 && !dateOutsideOfferWindow && offerUnlocked,
    queryFn: async ({ signal }) => {
      const payload = {
        therapy_ids: effectiveTherapies,
        package_id: initialPackage || null,
        offer_id: initialOffer || null,
        family_member_id: familyMember || null,
        service_at: preferredDate
          ? new Date(`${preferredDate}T${preferredTime || "12:00"}:00+05:30`).toISOString()
          : null,
      };
      try {
        return await requestJson<CommercialQuote>("/api/commercial/quote", {
          method: "POST", body: JSON.stringify(payload), signal,
        });
      } catch (error) { throw error; }
    },
  });
  const slotsQuery = useQuery({
    queryKey: ["customer-slots", effectiveTherapies, initialPackage, initialOffer, familyMember, preferredDate],
    enabled: customer && Boolean(effectiveTherapies[0]) && Boolean(preferredDate) && !dateOutsideOfferWindow && offerUnlocked,
    queryFn: ({ signal }) => {
      const query = new URLSearchParams({ therapy: effectiveTherapies[0], date: preferredDate });
      if (effectiveTherapies.length > 1) query.set("requested_therapies", effectiveTherapies.slice(1).join(","));
      if (initialPackage) query.set("package", initialPackage);
      if (initialOffer) query.set("offer", initialOffer);
      if (familyMember) query.set("family_member", familyMember);
      return requestJson<AvailableSlot[]>(`/api/availability/customer-slots?${query}`, { signal });
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
        selected_offer: quoteQuery.data?.offer_id === initialOffer ? initialOffer : null,
        preferred_date: preferredDate,
        preferred_time: preferredTime,
        pain_area: painArea.trim(),
        ...(differentAddress ? { service_address: serviceAddress, save_as_primary_address: savePrimaryAddress } : {}),
      }),
    }),
    onSuccess: setSubmitted,
  });

  const selectedNames = useMemo(() => (catalog?.therapies ?? []).filter((value) => effectiveTherapies.includes(value.id)).map((value) => value.name), [catalog, effectiveTherapies]);
  const offerWindow = selectedOffer ? `${selectedOffer.valid_from ? localDate(selectedOffer.valid_from) : "now"} to ${selectedOffer.valid_until ? inclusiveOfferEndDate(selectedOffer.valid_until) : "its end date"}` : "";
  const queryErrorMessage = (value: unknown) => value instanceof ClientApiError
    ? value.fieldErrors?.offer || value.fieldErrors?.therapies || value.message
    : value instanceof Error ? value.message : "Something went wrong. Please try again.";
  const changeDate = (value: string) => {
    setPreferredDate(value);
    setPreferredTime("");
    submit.reset();
  };
  const offerBenefit = selectedOffer
    ? selectedOffer.offer_type === "FIXED_DISCOUNT" ? `₹${Number(selectedOffer.discount_value).toLocaleString("en-IN")} OFF`
      : selectedOffer.offer_type === "PERCENTAGE" ? `${selectedOffer.discount_value}% OFF`
        : selectedOffer.offer_type === "FIXED_BUNDLE" ? `₹${Number(selectedOffer.fixed_price).toLocaleString("en-IN")} bundle price`
          : `Free ${selectedOffer.free_therapy_name}`
    : "";

  if (session.isPending || !customer) return <div className="card p-8 text-center text-slate-600">Confirming customer access…</div>;
  if (submitted) return <div className="card p-8 text-center" role="status"><p className="eyebrow">Request received</p><h2 className="mt-4 font-serif text-4xl text-[#103c27]">Booking request submitted successfully.</h2><dl className="mx-auto mt-5 grid max-w-sm gap-2 text-left"><div className="flex justify-between gap-4"><dt>Requested Date</dt><dd className="font-semibold">{submitted.preferred_date}</dd></div><div className="flex justify-between gap-4"><dt>Requested Time</dt><dd className="font-semibold">{submitted.preferred_time}</dd></div><div className="flex justify-between gap-4"><dt>Booking Submitted At</dt><dd className="font-semibold">{new Date(submitted.created_at).toLocaleString()}</dd></div><div className="flex justify-between gap-4"><dt>Status</dt><dd className="font-semibold">Awaiting confirmation</dd></div></dl><p className="mt-4 text-[#5b6c63]">Reference: <strong>{submitted.id}</strong></p></div>;

  const error = submit.error instanceof Error ? submit.error.message : "";
  return <form className="card space-y-7 p-5 sm:p-8" onSubmit={(event) => { event.preventDefault(); submit.mutate(); }}>
    <div><p className="eyebrow">Authenticated booking</p><h2 className="mt-2 font-serif text-3xl text-[#103c27]">Choose care and a preferred slot</h2><p className="mt-2 text-sm text-[#5b6c63]">Your verified profile and primary service address will be used automatically.</p></div>

    <section className="rounded-2xl border border-slate-200 p-4" aria-label="Booking service address"><h3 className="font-semibold text-[#163c2a]">Service address</h3>{profileQuery.isPending?<p className="mt-2 text-sm text-slate-600">Loading your primary service address…</p>:profileQuery.data?.address?<p className="mt-2 text-sm">{profileQuery.data.address.address_line_1}, {profileQuery.data.address.city}, {profileQuery.data.address.region} {profileQuery.data.address.pin_code}</p>:<p className="mt-2 text-sm text-amber-800">Your primary address could not be loaded.</p>}<label className="mt-3 flex items-center gap-2"><input type="checkbox" checked={differentAddress} onChange={event=>{const checked=event.target.checked;setDifferentAddress(checked);setServiceAddressConfirmed(false);if(checked)setServiceAddress(profileQuery.data?.address??emptyServiceAddress());else setSavePrimaryAddress(false)}}/>Use a different location for this booking</label></section>
    {differentAddress&&<><AddressCapture value={serviceAddress} onChange={setServiceAddress} title="One-time Service Address" onConfirmedChange={setServiceAddressConfirmed}/><label className="flex items-center gap-2"><input type="checkbox" checked={savePrimaryAddress} onChange={event=>setSavePrimaryAddress(event.target.checked)}/>Save this as my primary service address</label></>}

    {selectedOffer && <aside aria-label="Offer Summary" className="rounded-xl border border-emerald-200 bg-emerald-50 p-4"><p className="text-sm font-bold uppercase tracking-wide text-emerald-800">Offer: {selectedOffer.title}</p><p className="mt-1 text-xl font-bold text-[#103c27]">{offerBenefit}</p><p className="mt-1 font-semibold">Minimum required: {selectedOffer.minimum_therapy_count} eligible therapies</p><p className="mt-3">{eligibleSelectedCount} of {selectedOffer.minimum_therapy_count} therapies selected</p><p className={remainingTherapies ? "font-semibold text-amber-900" : "font-semibold text-emerald-800"}>{remainingTherapies ? `Select ${remainingTherapies} more eligible ${remainingTherapies === 1 ? "therapy" : "therapies"} to unlock this offer.` : `✓ Offer unlocked — ${offerBenefit.toLowerCase()} applied`}</p></aside>}
    <fieldset><legend className="font-semibold text-[#163c2a]">Therapy / therapies</legend><div className="mt-3 grid gap-3 sm:grid-cols-2">{catalog?.therapies.map((therapy) => { const selected = effectiveTherapies.includes(therapy.id); return <button type="button" key={therapy.id} aria-pressed={selected} onClick={() => { setSelectedTherapies(selected ? effectiveTherapies.filter((value) => value !== therapy.id) : [...effectiveTherapies, therapy.id]); setPreferredTime(""); }} className={`rounded-xl border p-4 text-left ${selected ? "border-emerald-700 bg-emerald-50" : "border-slate-200"}`}><span className="font-semibold">{therapy.name}</span><span className="mt-1 block text-sm text-slate-600">₹{Number(therapy.base_price ?? 0).toLocaleString("en-IN")}</span></button>; })}</div></fieldset>

    <label className="grid gap-2 font-semibold text-[#163c2a]">Booking for<select value={familyMember} onChange={(event) => { setFamilyMember(event.target.value); setPreferredTime(""); }} className="min-h-12 rounded-xl border border-slate-300 px-4 font-normal"><option value="">Myself</option>{familyQuery.data?.map((member) => <option key={member.id} value={member.id}>{member.full_name} ({member.relationship})</option>)}</select></label>
    <button type="button" className="text-left text-sm font-semibold text-emerald-800 underline" onClick={() => setAddingFamily((value) => !value)}>Add another patient</button>
    {addingFamily && <div className="grid gap-4 rounded-xl bg-emerald-50 p-4 sm:grid-cols-2">
      <label className="grid gap-1 text-sm font-semibold">Full name<input className="min-h-11 rounded-lg border px-3" value={familyDraft.full_name} onChange={(event) => setFamilyDraft({ ...familyDraft, full_name: event.target.value })} /></label>
      <label className="grid gap-1 text-sm font-semibold">Relationship<input className="min-h-11 rounded-lg border px-3" value={familyDraft.relationship} onChange={(event) => setFamilyDraft({ ...familyDraft, relationship: event.target.value })} /></label>
      <label className="grid gap-1 text-sm font-semibold">Age<input type="number" className="min-h-11 rounded-lg border px-3" value={familyDraft.age} onChange={(event) => setFamilyDraft({ ...familyDraft, age: event.target.value })} /></label>
      <label className="grid gap-1 text-sm font-semibold">Gender<select className="min-h-11 rounded-lg border px-3" value={familyDraft.gender} onChange={(event) => setFamilyDraft({ ...familyDraft, gender: event.target.value })}><option value="">Select</option><option value="FEMALE">Female</option><option value="MALE">Male</option><option value="OTHER">Other</option><option value="PREFER_NOT_TO_SAY">Prefer not to say</option></select></label>
      <button type="button" disabled={createFamily.isPending} onClick={() => createFamily.mutate()} className="button-secondary sm:col-span-2">{createFamily.isPending ? "Adding…" : "Add patient"}</button>
    </div>}

    <div className="grid gap-5 sm:grid-cols-2"><label className="grid gap-2 font-semibold text-[#163c2a]">Date<input type="date" required min={minDate} max={maxDate} disabled={offerUnavailable} value={preferredDate} onChange={(event) => changeDate(event.target.value)} className="min-h-12 rounded-xl border border-slate-300 px-4 font-normal" /></label><label className="grid gap-2 font-semibold text-[#163c2a]">Available time slot<select required disabled={!preferredDate || slotsQuery.isPending || slotsQuery.isError} value={preferredTime} onChange={(event) => setPreferredTime(event.target.value)} className="min-h-12 rounded-xl border border-slate-300 px-4 font-normal"><option value="">{slotsQuery.isPending ? "Loading available slots…" : "Select a time"}</option>{slotsQuery.data?.map((slot) => <option key={slot.value} value={slot.value}>{slot.label}</option>)}</select></label></div>
    {preferredDate && slotsQuery.data?.length === 0 && <p role="status" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">No appointment slots are available for this date.</p>}
    {offerUnavailable && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">This offer is no longer available for booking.</p>}
    {dateOutsideOfferWindow && <p role="alert" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">This offer is valid only for appointments from {offerWindow}.</p>}
    {selectedOffer && !offerUnlocked && <p role="status" className="rounded-xl bg-amber-50 p-3 text-sm font-semibold text-amber-900">Offer requirement not yet met. Select {remainingTherapies} more eligible {remainingTherapies === 1 ? "therapy" : "therapies"} to use this offer.</p>}
    {slotsQuery.isError && <p role="alert" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">{queryErrorMessage(slotsQuery.error)}</p>}
    <label className="grid gap-2 font-semibold text-[#163c2a]">Pain area (optional)<input value={painArea} maxLength={160} onChange={(event) => setPainArea(event.target.value)} className="min-h-12 rounded-xl border border-slate-300 px-4 font-normal" /></label>

    {selectedOffer && <p className="text-sm text-slate-600">Offer appointment window: {offerWindow}. Slots on the final date are limited by the exact offer end time.</p>}
    {quoteQuery.isError && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">{queryErrorMessage(quoteQuery.error)}</p>}
    {quoteQuery.data && <div className="rounded-xl bg-[#f7f3e9] p-4"><p className="font-semibold text-[#163c2a]">{selectedNames.join(" + ")}</p><p className="mt-2 text-sm">Duration: {quoteQuery.data.duration_minutes} minutes</p><p className="mt-1 text-xl font-bold text-emerald-800">₹{Number(quoteQuery.data.final_amount).toLocaleString("en-IN")}</p>{Number(quoteQuery.data.discount_amount) > 0 && <p className="text-sm text-slate-600">You save ₹{Number(quoteQuery.data.discount_amount).toLocaleString("en-IN")}</p>}</div>}
    {(error || createFamily.error) && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">{error || (createFamily.error instanceof Error ? createFamily.error.message : "The patient could not be added.")}</p>}
    <button disabled={submit.isPending || offerUnavailable || dateOutsideOfferWindow || !offerUnlocked || !effectiveTherapies.length || !preferredDate || !preferredTime || quoteQuery.isPending || quoteQuery.isError || (differentAddress&&!serviceAddressConfirmed)} className="button-primary w-full disabled:opacity-50">{submit.isPending ? "Booking…" : "Confirm Book Appointment"}</button>
    {submit.error instanceof ClientApiError && submit.error.fieldErrors && <ul className="text-sm text-red-700">{Object.values(submit.error.fieldErrors).map((value) => <li key={value}>{value}</li>)}</ul>}
  </form>;
}
