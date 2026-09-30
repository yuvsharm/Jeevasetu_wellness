"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Image from "next/image";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useSession } from "@/components/auth/session-provider";
import { TherapySelectionCard } from "@/components/appointments/therapy-selection-card";
import { AddressCapture } from "@/components/location/address-capture";
import { ClientApiError, requestJson } from "@/lib/api/client";
import type { AppointmentRequest, CommercialCatalog, CommercialQuote } from "@/lib/appointments/contracts";
import { activeRoles } from "@/lib/auth/roles";
import { emptyServiceAddress, type ServiceAddress } from "@/lib/location/contracts";

type FamilyMember = { id: string; full_name: string; age: number; gender: string; relationship: string };
type AvailableSlot = { value: string; label: string };
const OWNER_UPI_ID = "7351150555@ptsbi";
const OWNER_QR_PATH = "/images/payments/jeevasetu-owner-upi-qr.png";
const CLINIC_TIME_ZONE = "Asia/Kolkata";
const localDate = (value: Date | string) => new Intl.DateTimeFormat("en-CA", {
  timeZone: CLINIC_TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit",
}).format(new Date(value));
const inclusiveOfferEndDate = (value: string) => localDate(new Date(new Date(value).getTime() - 1));
const customerDateTime = (date: string, time: string) => {
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const [year, month, day] = date.split("-").map(Number);
  const [hour, minute] = time.split(":").map(Number);
  const displayHour = hour % 12 || 12;
  return `${String(day).padStart(2, "0")} ${months[month - 1]} ${year} · ${displayHour}:${String(minute).padStart(2, "0")} ${hour >= 12 ? "PM" : "AM"}`;
};

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
  const [stage, setStage] = useState<"details" | "review" | "payment" | "pending">("details");
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
    onSuccess: (value) => {
      setSubmitted(value);
      setStage("payment");
    },
  });
  const confirmationQuery = useQuery({
    queryKey: ["prepaid-booking-confirmation", submitted?.id],
    queryFn: () => requestJson<AppointmentRequest>(`/api/appointment-requests/${submitted!.id}`),
    enabled: stage === "pending" && Boolean(submitted?.id),
    refetchInterval: 5_000,
  });

  const selectedNames = useMemo(() => (catalog?.therapies ?? []).filter((value) => effectiveTherapies.includes(value.id)).map((value) => value.name), [catalog, effectiveTherapies]);
  const accountHolderName = [session.data?.user.first_name, session.data?.user.last_name].filter(Boolean).join(" ") || "Myself";
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
  const currentSubmission = confirmationQuery.data ?? submitted;
  if (currentSubmission?.appointment?.payment_status === "PAID") return <PaymentConfirmed request={currentSubmission} />;
  if (submitted && stage === "pending") return <PaymentDetailsReceived request={currentSubmission ?? submitted} />;
  if (submitted && stage === "payment") return <AppointmentPayment request={submitted} onSubmitted={(appointment)=>{setSubmitted(current=>current?{...current,appointment:appointment??current.appointment}:current);setStage("pending")}}/>;
  if (stage === "review") return <section className="card p-5 sm:p-8"><p className="eyebrow">Review booking</p><h2 className="mt-2 font-serif text-3xl text-[#103c27]">Check the visit before payment</h2><dl className="mt-5 grid gap-4 text-sm sm:grid-cols-2"><ReviewInfo label="Recipient" value={familyQuery.data?.find(value=>value.id===familyMember)?.full_name||accountHolderName}/><ReviewInfo label="Therapies" value={selectedNames.join(", ")}/><ReviewInfo label="Date and time" value={customerDateTime(preferredDate,preferredTime)}/><ReviewInfo label="Amount" value={quoteQuery.data?`₹${Number(quoteQuery.data.final_amount).toLocaleString("en-IN")}`:"Unavailable"}/><ReviewInfo label="Service address" value={differentAddress?`${serviceAddress.address_line_1}, ${serviceAddress.city}, ${serviceAddress.region} ${serviceAddress.pin_code}`:profileQuery.data?.address?`${profileQuery.data.address.address_line_1}, ${profileQuery.data.address.city}, ${profileQuery.data.address.region} ${profileQuery.data.address.pin_code}`:"Unavailable"}/></dl><div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"><button type="button" className="button-secondary" onClick={()=>setStage("details")}>Edit details</button><button type="button" disabled={submit.isPending} className="button-primary" onClick={()=>submit.mutate()}>{submit.isPending?"Preparing payment…":"Proceed to Payment"}</button></div>{submit.isError&&<p role="alert" className="mt-3 text-red-700">{submit.error.message}</p>}</section>;

  const error = submit.error instanceof Error ? submit.error.message : "";
  return <form className="card space-y-7 p-5 sm:p-8" onSubmit={(event) => { event.preventDefault(); submit.reset(); setStage("review"); }}>
    <div><p className="eyebrow">Authenticated booking</p><h2 className="mt-2 font-serif text-3xl text-[#103c27]">Choose care and a preferred slot</h2><p className="mt-2 text-sm text-[#5b6c63]">Your verified profile and primary service address will be used automatically.</p></div>

    <section className="rounded-2xl border border-slate-200 p-4" aria-label="Booking service address"><h3 className="font-semibold text-[#163c2a]">Service address</h3>{profileQuery.isPending?<p className="mt-2 text-sm text-slate-600">Loading your primary service address…</p>:profileQuery.data?.address?<p className="mt-2 text-sm">{profileQuery.data.address.address_line_1}, {profileQuery.data.address.city}, {profileQuery.data.address.region} {profileQuery.data.address.pin_code}</p>:<p className="mt-2 text-sm text-amber-800">Your primary address could not be loaded.</p>}<label className="mt-3 flex items-center gap-2"><input type="checkbox" checked={differentAddress} onChange={event=>{const checked=event.target.checked;setDifferentAddress(checked);setServiceAddressConfirmed(false);if(checked)setServiceAddress(profileQuery.data?.address??emptyServiceAddress());else setSavePrimaryAddress(false)}}/>Use a different location for this booking</label></section>
    {differentAddress&&<><AddressCapture value={serviceAddress} onChange={setServiceAddress} title="One-time Service Address" onConfirmedChange={setServiceAddressConfirmed}/><label className="flex items-center gap-2"><input type="checkbox" checked={savePrimaryAddress} onChange={event=>setSavePrimaryAddress(event.target.checked)}/>Save this as my primary service address</label></>}

    {selectedOffer && <aside aria-label="Offer Summary" className="rounded-xl border border-emerald-200 bg-emerald-50 p-4"><p className="text-sm font-bold uppercase tracking-wide text-emerald-800">Offer: {selectedOffer.title}</p><p className="mt-1 text-xl font-bold text-[#103c27]">{offerBenefit}</p><p className="mt-1 font-semibold">Minimum required: {selectedOffer.minimum_therapy_count} eligible therapies</p><p className="mt-3">{eligibleSelectedCount} of {selectedOffer.minimum_therapy_count} therapies selected</p><p className={remainingTherapies ? "font-semibold text-amber-900" : "font-semibold text-emerald-800"}>{remainingTherapies ? `Select ${remainingTherapies} more eligible ${remainingTherapies === 1 ? "therapy" : "therapies"} to unlock this offer.` : `✓ Offer unlocked — ${offerBenefit.toLowerCase()} applied`}</p></aside>}
    <fieldset className="min-w-0"><legend className="font-semibold text-[#163c2a]">Therapy / therapies</legend><div className="mt-3 grid min-w-0 gap-3 sm:grid-cols-2">{catalog?.therapies.map((therapy) => { const selected = effectiveTherapies.includes(therapy.id); return <TherapySelectionCard key={therapy.id} therapy={therapy} selected={selected} onToggle={() => { setSelectedTherapies(selected ? effectiveTherapies.filter((value) => value !== therapy.id) : [...effectiveTherapies, therapy.id]); setPreferredTime(""); }} />; })}</div></fieldset>

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
    <button disabled={offerUnavailable || dateOutsideOfferWindow || !offerUnlocked || !effectiveTherapies.length || !preferredDate || !preferredTime || quoteQuery.isPending || quoteQuery.isError || (differentAddress&&!serviceAddressConfirmed)} className="button-primary w-full disabled:opacity-50">Review Booking</button>
    {submit.error instanceof ClientApiError && submit.error.fieldErrors && <ul className="text-sm text-red-700">{Object.values(submit.error.fieldErrors).map((value) => <li key={value}>{value}</li>)}</ul>}
  </form>;
}

export function AppointmentPayment({request,onSubmitted}:{request:AppointmentRequest;onSubmitted:(appointment:AppointmentRequest["appointment"])=>void}){
  const [paymentAcknowledged,setPaymentAcknowledged]=useState(false);
  const [copyState,setCopyState]=useState<"idle"|"copied"|"error">("idle");
  const paymentSubmission=useMutation({
    mutationFn:(appointmentId:string)=>requestJson<AppointmentRequest["appointment"]>(`/api/schedule/my-appointments/${appointmentId}/payment-submission`,{method:"POST",body:JSON.stringify({acknowledged:true})}),
    onSuccess:onSubmitted,
  });
  const appointmentId=request.appointment?.id;
  return <section className="card mx-auto max-w-2xl overflow-hidden"><div className="max-h-[85vh] overflow-y-auto p-5 sm:p-8"><p className="eyebrow">Secure prepaid booking</p><h2 className="mt-2 font-serif text-3xl text-[#103c27]">Complete payment</h2><PaymentSummary request={request}/><div className="mx-auto mt-5 w-full max-w-72 overflow-hidden rounded-2xl bg-white"><div className="relative aspect-[1012/1181] w-full overflow-hidden"><Image src={OWNER_QR_PATH} alt="NuriPain Ease owner UPI payment QR code" width={1012} height={1601} unoptimized className="absolute inset-x-0 h-auto w-full max-w-none" style={{top:"-35.56%"}}/></div></div><div className="mt-4 rounded-xl bg-slate-50 p-4"><span className="text-xs font-bold uppercase tracking-wide text-slate-500">UPI ID</span><div className="mt-1 flex flex-wrap items-center justify-between gap-2"><code className="break-all text-base font-bold">{OWNER_UPI_ID}</code><button type="button" onClick={async()=>{try{await navigator.clipboard.writeText(OWNER_UPI_ID);setCopyState("copied")}catch{setCopyState("error")}}} className="min-h-11 rounded-xl border border-emerald-700 px-4 font-bold text-emerald-800">Copy</button></div>{copyState==="copied"&&<p role="status" className="mt-1 text-sm font-semibold text-emerald-800">UPI ID copied.</p>}{copyState==="error"&&<p role="alert" className="mt-1 text-sm text-red-700">Copy is unavailable. Select the UPI ID above.</p>}</div><PaymentTerms/><label className="mt-5 flex items-start gap-3 rounded-xl border border-amber-300 bg-amber-50 p-4 font-semibold"><input type="checkbox" checked={paymentAcknowledged} onChange={event=>setPaymentAcknowledged(event.target.checked)} className="mt-1 size-5"/>I understand and accept the payment and booking terms above.</label><button type="button" disabled={!appointmentId||!paymentAcknowledged||paymentSubmission.isPending} onClick={()=>appointmentId&&paymentSubmission.mutate(appointmentId)} className="button-primary mt-4 w-full disabled:opacity-50">{paymentSubmission.isPending?"Submitting…":"I Have Paid"}</button>{paymentSubmission.isError&&<p role="alert" className="mt-3 text-red-700">{paymentSubmission.error.message}</p>}</div></section>;
}

function PaymentTerms(){return <aside className="mt-5 rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950"><h3 className="font-bold">Important payment terms</h3><ul className="mt-2 list-disc space-y-1 pl-5"><li>Payment is required to confirm booking.</li><li>Payment is non-refundable.</li><li>A confirmed appointment cannot be cancelled or refunded through the normal booking flow.</li><li>Slot and therapist confirmation follow payment verification.</li></ul></aside>}
function PaymentSummary({request}:{request:AppointmentRequest}){const a=request.appointment;return <dl className="mt-5 grid gap-3 rounded-2xl bg-[#f7f3e9] p-4 text-sm sm:grid-cols-2"><ReviewInfo label="Recipient" value={request.family_member_name||request.patient_name}/><ReviewInfo label="Therapies" value={(request.requested_therapy_names?.length?request.requested_therapy_names:[request.therapy_name]).join(", ")}/><ReviewInfo label="Date and time" value={`${request.preferred_date} at ${request.preferred_time.slice(0,5)}`}/><ReviewInfo label="Amount" value={a?.payment_amount_due?`₹${a.payment_amount_due}`:`₹${request.final_amount??"0.00"}`}/><ReviewInfo label="Address" value={`${request.address}, ${request.city}, ${request.region??""} ${request.pin_code}`}/></dl>}
function PaymentDetailsReceived({request}:{request:AppointmentRequest}){
  const amount=request.appointment?.payment_amount_due??request.final_amount??"0.00";
  const therapies=(request.requested_therapy_names?.length?request.requested_therapy_names:[request.therapy_name]).join(", ");
  const address=[request.address,request.landmark,request.city,request.region,request.pin_code].filter(Boolean).join(", ");
  const [date,time]=customerDateTime(request.preferred_date,request.preferred_time).split(" · ");
  const steps=["Payment Details Received","Final Confirmation","Therapist Assigned","Therapy at Your Doorstep"];
  return <section role="status" className="card mx-auto max-w-4xl overflow-hidden border border-emerald-100">
    <div className="relative overflow-hidden bg-gradient-to-br from-[#0d4b32] via-emerald-700 to-emerald-600 px-5 py-8 text-white sm:px-10 sm:py-10">
      <div aria-hidden="true" className="absolute -right-16 -top-20 size-56 rounded-full bg-white/10"/>
      <div aria-hidden="true" className="absolute -bottom-20 -left-16 size-52 rounded-full bg-amber-200/10"/>
      <div className="relative">
        <div aria-hidden="true" className="mb-5 flex size-14 items-center justify-center rounded-full border border-white/40 bg-white/15 text-3xl shadow-lg">✓</div>
        <h2 className="max-w-3xl font-serif text-3xl leading-tight sm:text-4xl">Congratulations! Your Therapy is Just One Step Away from Your Doorstep</h2>
        <p className="mt-4 text-lg font-bold text-emerald-50 sm:text-xl">Payment details received successfully.</p>
        <p className="mt-2 max-w-2xl text-base leading-7 text-emerald-50 sm:text-lg">Your preferred therapy slot has been secured and our care team is completing the final confirmation.</p>
      </div>
    </div>
    <div className="p-5 sm:p-10">
      <h3 className="font-serif text-2xl text-[#103c27]">Your booking summary</h3>
      <dl className="mt-5 grid gap-4 rounded-2xl border border-emerald-100 bg-[#fbf9f2] p-5 text-sm sm:grid-cols-2 lg:grid-cols-3">
        <ReviewInfo label="Account Holder" value={request.account_holder_name||request.patient_name}/>
        <ReviewInfo label="Therapy Recipient" value={request.family_member_name||request.patient_name}/>
        <ReviewInfo label="Therapies" value={therapies}/>
        <ReviewInfo label="Date" value={date}/>
        <ReviewInfo label="Time" value={time}/>
        <ReviewInfo label="Amount" value={`₹${Number(amount).toLocaleString("en-IN")}`}/>
        <div className="sm:col-span-2 lg:col-span-3"><ReviewInfo label="Service Address" value={address}/></div>
      </dl>
      <div className="mt-7 rounded-2xl border border-emerald-200 bg-emerald-50/70 p-5 sm:p-6">
        <h3 className="font-serif text-2xl text-emerald-950">What happens next</h3>
        <ol className="mt-5 grid gap-3 sm:grid-cols-4" aria-label="Booking progress">
          {steps.map((step,index)=><li key={step} className="relative flex items-center gap-3 rounded-xl bg-white p-3 text-sm font-bold text-emerald-950 shadow-sm sm:min-h-24 sm:flex-col sm:justify-center sm:text-center">{index>0&&<span aria-hidden="true" className="text-xl text-amber-600 sm:absolute sm:-left-3">→</span>}<span className={`flex size-8 shrink-0 items-center justify-center rounded-full ${index===0?"bg-emerald-700 text-white":"border-2 border-emerald-300 bg-emerald-50 text-emerald-800"}`}>{index===0?"✓":index+1}</span><span>{step}</span></li>)}
        </ol>
      </div>
      <p className="mt-6 text-center text-base font-semibold text-[#355847]">We’ll notify you as soon as your therapist is assigned.</p>
    </div>
  </section>
}
function PaymentConfirmed({request}:{request:AppointmentRequest}){const a=request.appointment!;return <section className="card mx-auto max-w-3xl overflow-hidden"><div className="bg-gradient-to-br from-emerald-800 to-emerald-600 p-6 text-white sm:p-8"><p className="text-sm font-bold uppercase tracking-widest text-emerald-100">Payment Confirmed</p><h2 className="mt-2 font-serif text-4xl">Appointment Booked</h2><p className="mt-2 text-emerald-50">The Owner has verified your payment.</p></div><div className="p-5 sm:p-8"><dl className="grid gap-4 text-sm sm:grid-cols-2"><ReviewInfo label="Account holder" value={request.account_holder_name||request.patient_name}/><ReviewInfo label="Patient / Recipient" value={request.family_member_name||request.patient_name}/><ReviewInfo label="Therapies" value={(request.requested_therapy_names?.length?request.requested_therapy_names:[request.therapy_name]).join(", ")}/><ReviewInfo label="Date" value={request.preferred_date}/><ReviewInfo label="Time" value={request.preferred_time.slice(0,5)}/><ReviewInfo label="Amount / payment status" value={`₹${a.payment_amount_due??request.final_amount??"0.00"} · Paid`}/><ReviewInfo label="Address" value={[a.address_line_1,a.address_line_2,a.landmark,a.city,a.region,a.pin_code].filter(Boolean).join(", ")}/></dl><div className="mt-6 rounded-2xl bg-emerald-50 p-5"><h3 className="font-bold text-emerald-950">What happens next</h3><ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-emerald-950"><li>The Owner assigns an eligible therapist.</li><li>Your therapist reviews and accepts the visit.</li><li>You receive updates as the therapist travels and the therapy begins.</li><li>The therapist marks Therapy Done after the visit.</li></ol></div></div></section>}
function ReviewInfo({label,value}:{label:string;value:string}){return <div><dt className="font-semibold text-slate-600">{label}</dt><dd className="break-words font-medium text-slate-950">{value}</dd></div>}
