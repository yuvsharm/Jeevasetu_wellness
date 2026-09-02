"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { ClientApiError, requestJson } from "@/lib/api/client";
import type { CommercialOffer, TherapyOption, TherapyPackage } from "@/lib/appointments/contracts";

type Style = "PERCENTAGE" | "FIXED" | "COMBO" | "FREE" | "FAMILY";
type ComboBenefit = "PERCENTAGE" | "FINAL_PRICE";
type FamilyBenefit = "PERCENTAGE" | "FIXED" | "FREE";
type ErrorKey = "title" | "therapies" | "discount" | "freeTherapy" | "familyMembers" | "validFrom" | "validUntil" | "form";
type FormErrors = Partial<Record<ErrorKey, string>>;
type OfferForm = {
  title: string;
  style: Style;
  therapies: string[];
  discount: string;
  finalComboPrice: string;
  comboBenefit: ComboBenefit;
  familyBenefit: FamilyBenefit;
  minimumFamilyMembers: number;
  minimumTherapyCount: number;
  freeTherapy: string;
  validFrom: string;
  validUntil: string;
  message: string;
};

const emptyForm = (): OfferForm => ({
  title: "", style: "PERCENTAGE", therapies: [], discount: "", finalComboPrice: "",
  comboBenefit: "PERCENTAGE", familyBenefit: "PERCENTAGE", minimumFamilyMembers: 2, minimumTherapyCount: 1,
  freeTherapy: "", validFrom: "", validUntil: "", message: "",
});

const styles: Array<{ value: Style; title: string; help: string }> = [
  { value: "PERCENTAGE", title: "Percentage Discount", help: "Give the same percentage off selected therapies." },
  { value: "FIXED", title: "Fixed ₹ Discount", help: "Subtract one rupee amount from selected therapies." },
  { value: "COMBO", title: "Combo Discount", help: "Reward booking two or more therapies together." },
  { value: "FREE", title: "Buy Therapies + Get Therapy Free", help: "Choose paid therapies and one free therapy." },
  { value: "FAMILY", title: "Family Offer", help: "Apply a benefit to registered family bookings." },
];

const displayDate = (value: string | null) => value
  ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeZone: "Asia/Kolkata" }).format(new Date(value))
  : "No date limit";
const inputDate = (value: string | null) => value
  ? new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value))
  : "";
const offerBoundary = (date: string, endExclusive = false) => {
  const day = new Date(`${date}T00:00:00Z`);
  if (endExclusive) day.setUTCDate(day.getUTCDate() + 1);
  return new Date(`${day.toISOString().slice(0, 10)}T00:00:00+05:30`).toISOString();
};
const ErrorText = ({ children }: { children?: string }) => children
  ? <span role="alert" className="text-sm font-semibold text-red-700">{children}</span>
  : null;

export function CommercialManagement() {
  const queryClient = useQueryClient();
  const therapies = useQuery({ queryKey: ["commercial-therapies"], queryFn: () => requestJson<TherapyOption[]>("/api/commercial/therapies") });
  const packages = useQuery({ queryKey: ["commercial-packages"], queryFn: () => requestJson<TherapyPackage[]>("/api/commercial/packages") });
  const offers = useQuery({ queryKey: ["commercial-offers"], queryFn: () => requestJson<CommercialOffer[]>("/api/commercial/offers") });
  const [form, setForm] = useState<OfferForm>(emptyForm);
  const [errors, setErrors] = useState<FormErrors>({});
  const [success, setSuccess] = useState("");
  const [createDone, setCreateDone] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [expandedOfferId, setExpandedOfferId] = useState<string | null>(null);
  const [deactivateTarget, setDeactivateTarget] = useState<CommercialOffer | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CommercialOffer | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const submitLock = useRef(false);
  const [plan, setPlan] = useState({ name: "", therapy: "", session_count: 7, selling_price: "", description: "" });
  const activeTherapies = useMemo(() => (therapies.data ?? []).filter((therapy) => therapy.is_active), [therapies.data]);
  const paidTherapies = useMemo(() => activeTherapies.filter((therapy) => !therapy.is_offer_free_addon), [activeTherapies]);
  const therapyById = useMemo(() => new Map(activeTherapies.map((therapy) => [therapy.id, therapy])), [activeTherapies]);
  const selectedNames = form.therapies.map((id) => therapyById.get(id)?.name).filter(Boolean).join(", ");

  useEffect(() => {
    if (!createDone) return;
    const timer = window.setTimeout(() => {
      setCreateDone(false);
      setCreateOpen(false);
    }, 2500);
    return () => window.clearTimeout(timer);
  }, [createDone]);

  const refreshOffers = () => Promise.all([
    queryClient.invalidateQueries({ queryKey: ["commercial-offers"] }),
    queryClient.invalidateQueries({ queryKey: ["commercial-public"] }),
  ]);

  const validate = () => {
    const next: FormErrors = {};
    if (!form.title.trim()) next.title = "Please enter an offer name.";
    if (!form.therapies.length) next.therapies = "Please select at least one therapy.";
    else if (form.minimumTherapyCount < 1 || form.minimumTherapyCount > form.therapies.length) next.therapies = "Minimum eligible therapies cannot exceed the selected therapies.";
    if (form.style === "COMBO" && form.therapies.length < 2) next.therapies = "Please select at least two therapies for a combo.";
    const needsDiscount = form.style === "PERCENTAGE" || form.style === "FIXED"
      || (form.style === "COMBO" && form.comboBenefit === "PERCENTAGE")
      || (form.style === "FAMILY" && form.familyBenefit !== "FREE");
    if (needsDiscount && !Number(form.discount)) {
      next.discount = form.style === "FIXED" || form.familyBenefit === "FIXED"
        ? "Please enter the discount amount in rupees."
        : "Please enter the discount percentage.";
    }
    const percentageMode = form.style === "PERCENTAGE"
      || (form.style === "COMBO" && form.comboBenefit === "PERCENTAGE")
      || (form.style === "FAMILY" && form.familyBenefit === "PERCENTAGE");
    if (percentageMode && Number(form.discount) > 100) next.discount = "Discount percentage cannot exceed 100%.";
    if (form.style === "COMBO" && form.comboBenefit === "FINAL_PRICE" && !Number(form.finalComboPrice)) next.discount = "Please enter the final combo price in rupees.";
    if ((form.style === "FREE" || (form.style === "FAMILY" && form.familyBenefit === "FREE")) && !form.freeTherapy) next.freeTherapy = "Please select the free therapy.";
    if (form.style === "FAMILY" && form.minimumFamilyMembers < 2) next.familyMembers = "Minimum family members must be at least 2.";
    if (!form.validFrom) next.validFrom = "Please select the offer start date.";
    if (!form.validUntil) next.validUntil = "Please select the offer end date.";
    if (form.validFrom && form.validUntil && new Date(form.validUntil) <= new Date(form.validFrom)) next.validUntil = "Offer end date must be after the start date.";
    if (form.validUntil && new Date(form.validUntil) <= new Date()) next.validUntil = "Offer end date must be in the future.";
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const saveOffer = useMutation({
    mutationFn: async () => {
      setSuccess("");
      if (!validate()) throw new Error("validation");
      const familyFree = form.style === "FAMILY" && form.familyBenefit === "FREE";
      const freeOffer = form.style === "FREE" || familyFree;
      let offerType: CommercialOffer["offer_type"] = "PERCENTAGE";
      if (form.style === "FIXED") offerType = "FIXED_DISCOUNT";
      if (form.style === "COMBO") offerType = form.comboBenefit === "FINAL_PRICE" ? "FIXED_BUNDLE" : "PERCENTAGE";
      if (form.style === "FREE") offerType = "FREE_THERAPY";
      if (form.style === "FAMILY") offerType = familyFree ? "FAMILY_FREE" : "FAMILY";
      const fixedDiscount = form.style === "FIXED" || (form.style === "FAMILY" && form.familyBenefit === "FIXED");
      return requestJson<CommercialOffer>(editingId ? `/api/commercial/offers/${editingId}` : "/api/commercial/offers", {
        method: editingId ? "PATCH" : "POST",
        body: JSON.stringify({
          title: form.title.trim(),
          promotional_text: form.message.trim(),
          offer_type: offerType,
          eligible_therapies: form.therapies,
          minimum_therapy_count: form.style === "COMBO" ? form.therapies.length : form.minimumTherapyCount,
          maximum_therapy_count: form.style === "COMBO" ? form.therapies.length : null,
          discount_value: freeOffer || (form.style === "COMBO" && form.comboBenefit === "FINAL_PRICE") ? "0" : form.discount,
          fixed_price: form.style === "COMBO" && form.comboBenefit === "FINAL_PRICE" ? form.finalComboPrice : null,
          free_therapy: freeOffer ? form.freeTherapy : null,
          free_quantity: 1,
          family_required: form.style === "FAMILY",
          minimum_family_members: form.style === "FAMILY" ? form.minimumFamilyMembers : 1,
          rule_config: { discount_type: fixedDiscount ? "FIXED" : "PERCENTAGE" },
          valid_from: offerBoundary(form.validFrom),
          valid_until: offerBoundary(form.validUntil, true),
          is_active: true,
          is_publicly_visible: true,
          display_order: 0,
        }),
      });
    },
    onSuccess: async (savedOffer) => {
      queryClient.setQueryData<CommercialOffer[]>(["commercial-offers"], (current) => [savedOffer, ...(current ?? []).filter((offer) => offer.id !== savedOffer.id)]);
      setSuccess(editingId ? "Offer updated successfully." : "Offer created successfully.");
      if (!editingId) setCreateDone(true);
      else setCreateOpen(false);
      setErrors({});
      setForm(emptyForm());
      setEditingId(null);
      await refreshOffers();
    },
    onError: (error) => {
      if (error.message === "validation") return;
      if (error instanceof ClientApiError && error.fieldErrors) {
        setErrors({
          title: error.fieldErrors.title,
          therapies: error.fieldErrors.eligible_therapies,
          discount: error.fieldErrors.discount_value ?? error.fieldErrors.fixed_price,
          freeTherapy: error.fieldErrors.free_therapy,
          familyMembers: error.fieldErrors.minimum_family_members,
          validFrom: error.fieldErrors.valid_from,
          validUntil: error.fieldErrors.valid_until,
          form: error.message,
        });
      } else setErrors({ form: error.message });
    },
    onSettled: () => { submitLock.current = false; },
  });

  const deactivate = useMutation({
    mutationFn: (offer: CommercialOffer) => requestJson<CommercialOffer>(`/api/commercial/offers/${offer.id}`, { method: "PATCH", body: JSON.stringify({ is_active: false }) }),
    onSuccess: async (savedOffer) => {
      queryClient.setQueryData<CommercialOffer[]>(["commercial-offers"], (current) => (current ?? []).map((offer) => offer.id === savedOffer.id ? savedOffer : offer));
      setDeactivateTarget(null);
      setSuccess("Offer deactivated successfully.");
      await refreshOffers();
    },
    onError: (error) => { setDeactivateTarget(null); setErrors({ form: error.message }); },
  });
  const reactivate = useMutation({
    mutationFn: (offer: CommercialOffer) => requestJson<CommercialOffer>(`/api/commercial/offers/${offer.id}`, { method: "PATCH", body: JSON.stringify({ is_active: true }) }),
    onSuccess: async (savedOffer) => {
      queryClient.setQueryData<CommercialOffer[]>(["commercial-offers"], (current) => (current ?? []).map((offer) => offer.id === savedOffer.id ? savedOffer : offer));
      setSuccess("Offer reactivated successfully.");
      setErrors({});
      await refreshOffers();
    },
    onError: (error) => setErrors({ form: error.message }),
  });
  const removeOffer = useMutation({
    mutationFn: (offer: CommercialOffer) => requestJson<void>(`/api/commercial/offers/${offer.id}`, { method: "DELETE" }),
    onSuccess: async (_, offer) => {
      queryClient.setQueryData<CommercialOffer[]>(["commercial-offers"], (current) => (current ?? []).filter((item) => item.id !== offer.id));
      setDeleteTarget(null);
      setSuccess("Offer deleted successfully.");
      await refreshOffers();
    },
    onError: (error) => { setDeleteTarget(null); setErrors({ form: error.message }); },
  });
  const createPlan = useMutation({
    mutationFn: () => requestJson("/api/commercial/packages", { method: "POST", body: JSON.stringify({ ...plan, is_active: true, is_publicly_visible: true, display_order: 0 }) }),
    onSuccess: async () => {
      setPlan({ name: "", therapy: "", session_count: 7, selling_price: "", description: "" });
      await Promise.all([queryClient.invalidateQueries({ queryKey: ["commercial-packages"] }), queryClient.invalidateQueries({ queryKey: ["commercial-public"] })]);
    },
  });

  const changeStyle = (style: Style) => {
    setErrors({});
    setSuccess("");
    setForm((current) => ({ ...emptyForm(), title: current.title, style, validFrom: current.validFrom, validUntil: current.validUntil, message: current.message }));
  };
  const toggleTherapy = (id: string, checked: boolean) => {
    setErrors((current) => ({ ...current, therapies: undefined }));
    setForm((current) => ({ ...current, therapies: checked ? [...current.therapies, id] : current.therapies.filter((value) => value !== id) }));
  };
  const offerStatus = (offer: CommercialOffer) => !offer.is_active ? "Archived"
    : offer.valid_until && new Date(offer.valid_until) <= new Date()
    ? "Expired"
    : offer.valid_from && new Date(offer.valid_from) > new Date() ? "Upcoming" : "Active";

  const editOffer = (offer: CommercialOffer) => {
    let style: Style = "PERCENTAGE";
    if (offer.offer_type === "PERCENTAGE" && offer.minimum_therapy_count >= 2 && offer.maximum_therapy_count === offer.minimum_therapy_count) style = "COMBO";
    if (offer.offer_type === "FIXED_DISCOUNT") style = "FIXED";
    if (offer.offer_type === "FIXED_BUNDLE") style = "COMBO";
    if (offer.offer_type === "FREE_THERAPY") style = "FREE";
    if (offer.offer_type === "FAMILY" || offer.offer_type === "FAMILY_FREE") style = "FAMILY";
    const legacyRule = offer.rule_config.therapy_discounts?.[0];
    if (offer.offer_type === "THERAPY_DISCOUNT" && legacyRule?.discount_type === "FIXED") style = "FIXED";
    setEditingId(offer.id);
    setCreateOpen(true);
    setErrors({});
    setSuccess("");
    setForm({
      title: offer.title,
      style,
      therapies: offer.eligible_therapies,
      discount: offer.offer_type === "THERAPY_DISCOUNT" && legacyRule ? String(legacyRule.discount) : offer.discount_value,
      finalComboPrice: offer.fixed_price ?? "",
      comboBenefit: offer.offer_type === "FIXED_BUNDLE" ? "FINAL_PRICE" : "PERCENTAGE",
      familyBenefit: offer.offer_type === "FAMILY_FREE" ? "FREE" : offer.rule_config.discount_type === "FIXED" ? "FIXED" : "PERCENTAGE",
      minimumFamilyMembers: offer.minimum_family_members,
      minimumTherapyCount: offer.minimum_therapy_count,
      freeTherapy: offer.free_therapy ?? "",
      validFrom: inputDate(offer.valid_from),
      validUntil: offer.valid_until ? inputDate(new Date(new Date(offer.valid_until).getTime() - 1).toISOString()) : "",
      message: offer.promotional_text,
    });
    window.setTimeout(() => document.getElementById("offer-form")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  };

  const benefitText = (offer: CommercialOffer) => {
    if (offer.offer_type === "FREE_THERAPY" || offer.offer_type === "FAMILY_FREE") return `${offer.free_therapy_name} FREE`;
    if (offer.offer_type === "FIXED_BUNDLE") return `Final combo price ₹${offer.fixed_price}`;
    if (offer.offer_type === "THERAPY_DISCOUNT") return (offer.rule_config.therapy_discounts ?? []).map((rule) => `${therapyById.get(rule.therapy_id)?.name ?? "Therapy"}: ${rule.discount_type === "PERCENTAGE" ? `${rule.discount}%` : `₹${rule.discount}`}`).join(" · ");
    return offer.rule_config.discount_type === "FIXED" || offer.offer_type === "FIXED_DISCOUNT" ? `₹${offer.discount_value} off` : `${offer.discount_value}% off`;
  };

  const previewBenefit = form.style === "PERCENTAGE" ? `${form.discount || "—"}% off`
    : form.style === "FIXED" ? `₹${form.discount || "—"} off`
      : form.style === "COMBO" ? form.comboBenefit === "PERCENTAGE" ? `${form.discount || "—"}% combo discount` : `Final combo price ₹${form.finalComboPrice || "—"}`
        : form.style === "FREE" ? `${therapyById.get(form.freeTherapy)?.name ?? "Select a therapy"} FREE`
          : form.familyBenefit === "FREE" ? `${therapyById.get(form.freeTherapy)?.name ?? "Select a therapy"} FREE` : `${form.familyBenefit === "FIXED" ? "₹" : ""}${form.discount || "—"}${form.familyBenefit === "PERCENTAGE" ? "%" : ""} off`;

  return <section id="offers-packages" tabIndex={-1} className="mt-8 min-w-0 scroll-mt-24 space-y-6 focus:outline-none" aria-labelledby="offers-heading">
    <div className="flex flex-wrap items-start justify-between gap-4"><div><h2 id="offers-heading" className="text-2xl font-bold">Offers &amp; Packages</h2><p className="mt-1 text-slate-600">Manage customer offers without exposing technical pricing rules.</p></div><button type="button" aria-expanded={createOpen} aria-controls="offer-form" onClick={() => { setCreateOpen((open) => !open); setEditingId(null); setForm(emptyForm()); setErrors({}); setSuccess(""); }} className="min-h-11 rounded-xl bg-emerald-700 px-5 font-bold text-white">{createOpen && !editingId ? "Close Create Form" : "Create New Offer"}</button></div>
    <div aria-label="Offer status summary" className="grid gap-3 sm:grid-cols-4">{(["Active", "Upcoming", "Expired", "Archived"] as const).map((group) => <div key={group} className="rounded-xl border bg-white px-4 py-3"><p className="text-sm font-semibold text-slate-600">{group} Offers</p><p className="text-2xl font-bold text-slate-950">{(offers.data ?? []).filter((offer) => offerStatus(offer) === group).length}</p></div>)}</div>
    {offers.data?.length === 0 && <div className="rounded-xl border border-dashed bg-white p-5"><p className="font-bold text-slate-900">No offers created yet.</p><p className="mt-1 text-sm text-slate-600">Create your first offer to make a promotion available to customers.</p></div>}
    {success && <p role="status" aria-live="polite" className="fixed right-4 top-4 z-50 max-w-sm rounded-xl border border-emerald-200 bg-emerald-50 p-4 font-semibold text-emerald-900 shadow-xl">{success}</p>}
    {!createOpen && errors.form && <p role="alert" className="rounded-xl bg-red-50 p-3 text-red-800">{errors.form}</p>}

    <details className="rounded-2xl border bg-white p-5"><summary className="cursor-pointer text-xl font-bold">Session Packages</summary><form onSubmit={(event) => { event.preventDefault(); createPlan.mutate(); }} className="mt-4 grid gap-3 sm:grid-cols-2"><label className="grid gap-1 font-semibold">Package Name<input required value={plan.name} onChange={(event) => setPlan({ ...plan, name: event.target.value })} className="min-h-11 rounded-xl border px-3 font-normal" /></label><label className="grid gap-1 font-semibold">Therapy<select required value={plan.therapy} onChange={(event) => setPlan({ ...plan, therapy: event.target.value })} className="min-h-11 rounded-xl border px-3 font-normal"><option value="">Select therapy</option>{activeTherapies.map((therapy) => <option key={therapy.id} value={therapy.id}>{therapy.name}</option>)}</select></label><label className="grid gap-1 font-semibold">Number of Sessions<input required type="number" min="1" value={plan.session_count} onChange={(event) => setPlan({ ...plan, session_count: Number(event.target.value) })} className="min-h-11 rounded-xl border px-3 font-normal" /></label><label className="grid gap-1 font-semibold">Package Price (₹)<input required type="number" min="0" step=".01" value={plan.selling_price} onChange={(event) => setPlan({ ...plan, selling_price: event.target.value })} className="min-h-11 rounded-xl border px-3 font-normal" /></label><label className="grid gap-1 font-semibold sm:col-span-2">Package Description (Optional)<textarea value={plan.description} onChange={(event) => setPlan({ ...plan, description: event.target.value })} className="rounded-xl border p-3 font-normal" /></label><button className="min-h-11 rounded-xl bg-emerald-700 px-4 font-bold text-white sm:col-span-2">{createPlan.isPending ? "Creating..." : "Create Package"}</button>{createPlan.isError && <p role="alert" className="text-red-700 sm:col-span-2">{createPlan.error.message}</p>}</form><div className="mt-4 text-sm text-slate-600">{packages.data?.map((item) => <p key={item.id}>{item.name}: {item.session_count} sessions · ₹{item.selling_price}</p>)}</div></details>

    {createOpen && <form id="offer-form" noValidate onSubmit={(event) => { event.preventDefault(); if (submitLock.current) return; submitLock.current = true; saveOffer.mutate(); }} className="grid scroll-mt-24 gap-6 rounded-2xl border bg-white p-5">
      <div><h3 className="text-xl font-bold">{editingId ? "Edit Offer" : "Create an Offer"}</h3><p className="mt-1 text-sm text-slate-600">Technical pricing rules are handled securely in the background.</p></div>
      <label className="grid gap-2 font-semibold">Offer Name<input aria-label="Offer Name" value={form.title} onChange={(event) => { setErrors((current) => ({ ...current, title: undefined })); setForm({ ...form, title: event.target.value }); }} placeholder="September Wellness Offer" className="min-h-12 rounded-xl border px-4 font-normal" /><ErrorText>{errors.title}</ErrorText></label>

      <fieldset><legend className="font-semibold">Choose Offer Type</legend><div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{styles.map((option) => <label key={option.value} className={`cursor-pointer rounded-2xl border p-4 ${form.style === option.value ? "border-emerald-700 bg-emerald-50" : "border-slate-200"}`}><span className="flex items-start gap-2"><input type="radio" name="offer-style" checked={form.style === option.value} onChange={() => changeStyle(option.value)} /><span><strong className="block">{option.title}</strong><span className="mt-1 block text-sm text-slate-600">{option.help}</span></span></span></label>)}</div></fieldset>

      {form.style === "FAMILY" && <fieldset className="rounded-2xl bg-slate-50 p-4"><legend className="font-semibold">Family Benefit</legend><div className="mt-2 flex flex-wrap gap-4">{([["PERCENTAGE", "Percentage discount"], ["FIXED", "Fixed ₹ discount"], ["FREE", "Free therapy"]] as Array<[FamilyBenefit, string]>).map(([value, label]) => <label key={value}><input type="radio" name="family-benefit" checked={form.familyBenefit === value} onChange={() => setForm({ ...form, familyBenefit: value, discount: "", freeTherapy: "" })} /> {label}</label>)}</div><label className="mt-4 grid max-w-xs gap-1 font-semibold">Minimum Family Members<input aria-label="Minimum Family Members" type="number" min="2" value={form.minimumFamilyMembers} onChange={(event) => setForm({ ...form, minimumFamilyMembers: Number(event.target.value) })} className="min-h-11 rounded-xl border px-3 font-normal" /><span className="text-sm font-normal text-slate-600">At least this many registered family members are required.</span><ErrorText>{errors.familyMembers}</ErrorText></label></fieldset>}

      <fieldset><legend className="font-semibold">{form.style === "FREE" || (form.style === "FAMILY" && form.familyBenefit === "FREE") ? "Book These Therapies" : form.style === "COMBO" ? "Select 2 or More Therapies" : "Eligible Therapies"}</legend><p className="mt-1 text-sm text-slate-600">Select the therapies this offer applies to.</p><div className="mt-3 flex flex-wrap gap-2">{paidTherapies.map((therapy) => <label key={therapy.id} className={`rounded-full border px-3 py-2 ${form.therapies.includes(therapy.id) ? "border-emerald-700 bg-emerald-50" : "border-slate-200"}`}><input type="checkbox" checked={form.therapies.includes(therapy.id)} onChange={(event) => toggleTherapy(therapy.id, event.target.checked)} /> {therapy.name}</label>)}</div><ErrorText>{errors.therapies}</ErrorText></fieldset>
      {form.style !== "COMBO" && <label className="grid max-w-sm gap-1 font-semibold">Minimum Eligible Therapies<input aria-label="Minimum Eligible Therapies" type="number" min="1" max={Math.max(1, form.therapies.length)} value={form.minimumTherapyCount} onChange={(event) => setForm({ ...form, minimumTherapyCount: Number(event.target.value) })} className="min-h-11 rounded-xl border px-3 font-normal" /><span className="text-sm font-normal text-slate-600">Customers must select at least this many eligible therapies to unlock the offer.</span></label>}

      {form.style === "PERCENTAGE" && <label className="grid max-w-sm gap-1 font-semibold">Discount Percentage (%)<input aria-label="Discount Percentage (%)" type="number" min="0.01" max="100" step="0.01" value={form.discount} onChange={(event) => { setErrors((current) => ({ ...current, discount: undefined })); setForm({ ...form, discount: event.target.value }); }} placeholder="10" className="min-h-11 rounded-xl border px-3 font-normal" /><span className="text-sm font-normal text-slate-600">Example: enter 10 for 10% off.</span><ErrorText>{errors.discount}</ErrorText></label>}
      {form.style === "FIXED" && <label className="grid max-w-sm gap-1 font-semibold">Discount Amount (₹)<input aria-label="Discount Amount (₹)" type="number" min="0.01" step="0.01" value={form.discount} onChange={(event) => { setErrors((current) => ({ ...current, discount: undefined })); setForm({ ...form, discount: event.target.value }); }} placeholder="500" className="min-h-11 rounded-xl border px-3 font-normal" /><span className="text-sm font-normal text-slate-600">This rupee amount is deducted from the eligible booking.</span><ErrorText>{errors.discount}</ErrorText></label>}

      {form.style === "COMBO" && <fieldset className="rounded-2xl bg-slate-50 p-4"><legend className="font-semibold">Combo Benefit</legend><div className="mt-2 flex flex-wrap gap-5"><label><input type="radio" name="combo-benefit" checked={form.comboBenefit === "PERCENTAGE"} onChange={() => setForm({ ...form, comboBenefit: "PERCENTAGE", finalComboPrice: "" })} /> Discount %</label><label><input type="radio" name="combo-benefit" checked={form.comboBenefit === "FINAL_PRICE"} onChange={() => setForm({ ...form, comboBenefit: "FINAL_PRICE", discount: "" })} /> Final Combo Price ₹</label></div>{form.comboBenefit === "PERCENTAGE" ? <label className="mt-4 grid max-w-sm gap-1 font-semibold">Combo Discount (%)<input aria-label="Combo Discount (%)" type="number" min="0.01" max="100" step="0.01" value={form.discount} onChange={(event) => setForm({ ...form, discount: event.target.value })} placeholder="10" className="min-h-11 rounded-xl border px-3 font-normal" /><span className="text-sm font-normal text-slate-600">Percentage deducted from the combined therapy price.</span><ErrorText>{errors.discount}</ErrorText></label> : <label className="mt-4 grid max-w-sm gap-1 font-semibold">Final Combo Price (₹)<input aria-label="Final Combo Price (₹)" type="number" min="0.01" step="0.01" value={form.finalComboPrice} onChange={(event) => setForm({ ...form, finalComboPrice: event.target.value })} placeholder="3800" className="min-h-11 rounded-xl border px-3 font-normal" /><span className="text-sm font-normal text-slate-600">The final price for all selected therapies together.</span><ErrorText>{errors.discount}</ErrorText></label>}</fieldset>}

      {form.style === "FAMILY" && form.familyBenefit !== "FREE" && <label className="grid max-w-sm gap-1 font-semibold">{form.familyBenefit === "PERCENTAGE" ? "Family Discount (%)" : "Family Discount Amount (₹)"}<input aria-label={form.familyBenefit === "PERCENTAGE" ? "Family Discount (%)" : "Family Discount Amount (₹)"} type="number" min="0.01" max={form.familyBenefit === "PERCENTAGE" ? "100" : undefined} step="0.01" value={form.discount} onChange={(event) => setForm({ ...form, discount: event.target.value })} placeholder={form.familyBenefit === "PERCENTAGE" ? "10" : "500"} className="min-h-11 rounded-xl border px-3 font-normal" /><span className="text-sm font-normal text-slate-600">Applied only when the registered family-member requirement is met.</span><ErrorText>{errors.discount}</ErrorText></label>}
      {(form.style === "FREE" || (form.style === "FAMILY" && form.familyBenefit === "FREE")) && <label className="grid max-w-lg gap-1 font-semibold">Get This Therapy FREE<select aria-label="Get This Therapy FREE" value={form.freeTherapy} onChange={(event) => { setErrors((current) => ({ ...current, freeTherapy: undefined })); setForm({ ...form, freeTherapy: event.target.value }); }} className="min-h-12 rounded-xl border px-3 font-normal"><option value="">Select the free therapy</option>{activeTherapies.map((therapy) => <option key={therapy.id} value={therapy.id}>{therapy.name}</option>)}</select><span className="text-sm font-normal text-slate-600">This therapy is added as the free benefit.</span><ErrorText>{errors.freeTherapy}</ErrorText></label>}

      <fieldset><legend className="font-semibold">Offer Validity</legend><div className="mt-2 grid gap-3 sm:grid-cols-2"><label className="grid gap-1">Start Date<input aria-label="Start Date" type="date" value={form.validFrom} onChange={(event) => { setErrors((current) => ({ ...current, validFrom: undefined })); setForm({ ...form, validFrom: event.target.value }); }} className="min-h-11 rounded-xl border px-3" /><ErrorText>{errors.validFrom}</ErrorText></label><label className="grid gap-1">End Date<input aria-label="End Date" type="date" value={form.validUntil} onChange={(event) => { setErrors((current) => ({ ...current, validUntil: undefined })); setForm({ ...form, validUntil: event.target.value }); }} className="min-h-11 rounded-xl border px-3" /><ErrorText>{errors.validUntil}</ErrorText></label></div><p className="mt-2 text-sm text-slate-600">The offer remains valid throughout the selected end date in Asia/Kolkata.</p></fieldset>
      <label className="grid gap-1 font-semibold">Offer Message (Optional)<textarea aria-label="Offer Message (Optional)" value={form.message} onChange={(event) => setForm({ ...form, message: event.target.value })} className="rounded-xl border p-3 font-normal" /><span className="text-sm font-normal text-slate-600">This message will be shown to customers.</span></label>
      <aside className="rounded-2xl bg-emerald-50 p-4" aria-label="Offer preview"><p className="text-xs font-bold uppercase tracking-wider">Offer Preview</p><h3 className="mt-1 text-xl font-bold">{form.title || "Your offer name"}</h3><p>{form.style === "FAMILY" ? `Minimum ${form.minimumFamilyMembers} registered family members · ` : ""}{previewBenefit}</p><p>Therapies: {selectedNames || "Select therapies"}</p><p>Valid: {form.validFrom ? displayDate(new Date(form.validFrom).toISOString()) : "Select start"} – {form.validUntil ? displayDate(new Date(form.validUntil).toISOString()) : "Select end"}</p></aside>
      {errors.form && <p role="alert" className="rounded-xl bg-red-50 p-3 text-red-800">{errors.form}</p>}
      <div className="flex gap-3">{editingId && <button type="button" onClick={() => { setEditingId(null); setForm(emptyForm()); setErrors({}); setCreateOpen(false); }} className="min-h-12 rounded-xl border px-5 font-bold">Cancel Edit</button>}<button disabled={saveOffer.isPending || createDone} className="min-h-12 flex-1 rounded-xl bg-emerald-700 px-5 font-bold text-white disabled:opacity-60">{saveOffer.isPending ? editingId ? "Updating..." : "Creating..." : createDone && !editingId ? "Done ✓" : editingId ? "Update Offer" : "Create Offer"}</button></div>
    </form>}

    {(["Active", "Upcoming", "Expired", "Archived"] as const).map((group) => {
      const groupOffers = (offers.data ?? []).filter((offer) => offerStatus(offer) === group);
      return <section key={group} aria-labelledby={`${group.toLowerCase()}-offers-heading`}><div className="flex items-baseline justify-between gap-3"><h3 id={`${group.toLowerCase()}-offers-heading`} className="text-xl font-bold">{group} Offers</h3><span className="text-sm text-slate-500">{groupOffers.length}</span></div><div className="mt-3 space-y-2">{groupOffers.length === 0 && <p className="rounded-xl border border-dashed bg-white px-4 py-3 text-sm text-slate-500">No {group.toLowerCase()} offers.</p>}{groupOffers.map((offer) => {
        const expanded = expandedOfferId === offer.id;
        const expired = Boolean(offer.valid_until && new Date(offer.valid_until) <= new Date());
        return <article key={offer.id} className="rounded-xl border bg-white"><div className="flex flex-wrap items-center gap-x-4 gap-y-2 p-4"><button type="button" aria-expanded={expanded} aria-controls={`offer-details-${offer.id}`} onClick={() => setExpandedOfferId(expanded ? null : offer.id)} className="min-w-0 flex-1 text-left"><span className="flex items-center justify-between gap-3"><strong className="truncate text-slate-950">{offer.title}</strong><span aria-hidden="true" className="text-slate-500">{expanded ? "▴" : "▾"}</span></span><span className="mt-1 block text-sm font-semibold text-emerald-800">{benefitText(offer)}</span><span className="mt-1 block text-xs text-slate-500">{displayDate(offer.valid_from)} – {displayDate(offer.valid_until)}</span></button><span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-700">{group}</span><div className="flex flex-wrap gap-2"><button type="button" onClick={() => editOffer(offer)} className="min-h-9 rounded-lg border px-3 text-sm font-bold text-emerald-800">Edit</button>{offer.is_active ? <button type="button" onClick={() => setDeactivateTarget(offer)} className="min-h-9 rounded-lg border border-red-200 px-3 text-sm font-bold text-red-700">Deactivate</button> : <button type="button" onClick={() => expired ? editOffer(offer) : reactivate.mutate(offer)} disabled={reactivate.isPending} title={expired ? "Edit the validity dates before reactivating this expired offer." : undefined} className="min-h-9 rounded-lg border px-3 text-sm font-bold text-emerald-800">{expired ? "Edit to Reactivate" : "Reactivate"}</button>}<button type="button" onClick={() => setDeleteTarget(offer)} className="min-h-9 rounded-lg border border-red-200 px-3 text-sm font-bold text-red-700">Delete</button><button type="button" onClick={() => { editOffer(offer); setEditingId(null); setForm((current) => ({ ...current, title: `${offer.title} Copy` })); }} className="min-h-9 rounded-lg border px-3 text-sm font-bold text-emerald-800">Duplicate</button></div></div>{expanded && <div id={`offer-details-${offer.id}`} className="grid gap-3 border-t p-4 text-sm sm:grid-cols-2"><div><p className="font-bold text-slate-600">Eligible therapies</p><p>{offer.eligible_therapy_names.join(", ")}</p></div><div><p className="font-bold text-slate-600">Validity</p><p>{displayDate(offer.valid_from)} – {displayDate(offer.valid_until)}</p></div>{offer.promotional_text && <div className="sm:col-span-2"><p className="font-bold text-slate-600">Customer message</p><p>{offer.promotional_text}</p></div>}</div>}</article>;
      })}</div></section>;
    })}
    {deactivateTarget && <div role="dialog" aria-modal="true" aria-labelledby="deactivate-offer-heading" className="fixed inset-0 z-50 grid place-items-center bg-slate-950/50 p-4"><div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl"><h3 id="deactivate-offer-heading" className="text-xl font-bold">Deactivate this offer?</h3><p className="mt-3 text-slate-700"><strong>{deactivateTarget.title}</strong> will no longer be available to customers. Its booking history will remain intact.</p><div className="mt-5 flex justify-end gap-3"><button type="button" onClick={() => setDeactivateTarget(null)} className="min-h-11 rounded-xl border px-5 font-bold">Cancel</button><button type="button" disabled={deactivate.isPending} onClick={() => deactivate.mutate(deactivateTarget)} className="min-h-11 rounded-xl bg-red-700 px-5 font-bold text-white">{deactivate.isPending ? "Deactivating..." : "Deactivate"}</button></div></div></div>}
    {deleteTarget && <div role="dialog" aria-modal="true" aria-labelledby="delete-offer-heading" className="fixed inset-0 z-50 grid place-items-center bg-slate-950/50 p-4"><div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl"><h3 id="delete-offer-heading" className="text-xl font-bold">{deleteTarget.can_delete ? "Delete this offer permanently?" : `${deleteTarget.title} cannot be deleted`}</h3>{deleteTarget.can_delete ? <p className="mt-3 text-slate-700"><strong>{deleteTarget.title}</strong> will be permanently removed. This action cannot be undone.</p> : <p className="mt-3 text-slate-700">This offer has historical booking records and cannot be permanently deleted. Archive it instead.</p>}<div className="mt-5 flex justify-end gap-3"><button type="button" onClick={() => setDeleteTarget(null)} className="min-h-11 rounded-xl border px-5 font-bold">{deleteTarget.can_delete ? "Cancel" : "Close"}</button>{deleteTarget.can_delete && <button type="button" disabled={removeOffer.isPending} onClick={() => removeOffer.mutate(deleteTarget)} className="min-h-11 rounded-xl bg-red-700 px-5 font-bold text-white">{removeOffer.isPending ? "Deleting..." : "Delete permanently"}</button>}</div></div></div>}
  </section>;
}
