"use client";

import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClientApiError, requestJson } from "@/lib/api/client";
import type { TherapyOption } from "@/lib/appointments/contracts";

type Filter = "ALL" | "ACTIVE" | "INACTIVE";
type FormState = {
  name: string;
  slug: string;
  short_description: string;
  detailed_description: string;
  benefits: string;
  base_price: string;
  is_publicly_visible: boolean;
  display_order: number;
};
type FormErrors = Partial<Record<keyof FormState | "form", string>>;
type Confirmation = { therapy: TherapyOption; action: "DEACTIVATE" | "DELETE" } | null;

const emptyForm = (): FormState => ({
  name: "", slug: "", short_description: "", detailed_description: "", benefits: "",
  base_price: "", is_publicly_visible: true, display_order: 0,
});
const slugify = (value: string) => value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const money = (value?: string) => `₹${Number(value ?? 0).toLocaleString("en-IN")}`;

function ErrorText({ children }: { children?: string }) {
  return children ? <span role="alert" className="text-sm font-semibold text-red-700">{children}</span> : null;
}

export function TherapyManagement() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["commercial-therapies"], queryFn: () => requestJson<TherapyOption[]>("/api/commercial/therapies") });
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("ALL");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editing, setEditing] = useState<TherapyOption | null | undefined>(undefined);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [errors, setErrors] = useState<FormErrors>({});
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState("");
  const [confirmation, setConfirmation] = useState<Confirmation>(null);
  const submitLock = useRef(false);
  const slugTouched = useRef(false);

  const therapies = useMemo(() => {
    const term = search.trim().toLowerCase();
    return (query.data ?? []).filter((therapy) => {
      if (filter === "ACTIVE" && !therapy.is_active) return false;
      if (filter === "INACTIVE" && therapy.is_active) return false;
      return !term || therapy.name.toLowerCase().includes(term) || therapy.slug.toLowerCase().includes(term);
    });
  }, [filter, query.data, search]);

  const updateCache = (therapy: TherapyOption) => {
    queryClient.setQueryData<TherapyOption[]>(["commercial-therapies"], (current) => [
      therapy,
      ...(current ?? []).filter((item) => item.id !== therapy.id),
    ].sort((left, right) => (left.display_order ?? 0) - (right.display_order ?? 0) || left.name.localeCompare(right.name)));
  };
  const refreshPublic = () => queryClient.invalidateQueries({ queryKey: ["commercial-public"] });

  const validate = () => {
    const next: FormErrors = {};
    if (!form.name.trim()) next.name = "Please enter the therapy name.";
    if (!form.slug.trim()) next.slug = "Please enter a URL slug.";
    const price = Number(form.base_price);
    if (form.base_price === "" || Number.isNaN(price) || price < 0) next.base_price = "Please enter a valid price in rupees.";
    if (form.short_description.length > 240) next.short_description = "Short description must be 240 characters or fewer.";
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const save = useMutation({
    mutationFn: async () => {
      if (!validate()) throw new Error("validation");
      const payload = {
        name: form.name.trim(),
        slug: form.slug.trim(),
        short_description: form.short_description.trim(),
        detailed_description: form.detailed_description.trim(),
        benefits: form.benefits.split("\n").map((value) => value.trim()).filter(Boolean),
        default_duration_minutes: 45,
        base_price: form.base_price,
        is_active: editing?.is_active ?? true,
        is_publicly_visible: form.is_publicly_visible,
        display_order: form.display_order,
      };
      return requestJson<TherapyOption>(editing ? `/api/commercial/therapies/${editing.id}` : "/api/commercial/therapies", {
        method: editing ? "PATCH" : "POST",
        body: JSON.stringify(payload),
      });
    },
    onSuccess: async (therapy) => {
      updateCache(therapy);
      setActionError("");
      setNotice(editing ? "Therapy updated successfully." : "Therapy added successfully.");
      setEditing(undefined);
      setForm(emptyForm());
      setErrors({});
      await refreshPublic();
    },
    onError: (error) => {
      if (error.message === "validation") return;
      if (error instanceof ClientApiError && error.fieldErrors) {
        setErrors({ ...error.fieldErrors, form: error.message } as FormErrors);
      } else setErrors({ form: error.message });
    },
    onSettled: () => { submitLock.current = false; },
  });

  const changeStatus = useMutation({
    onMutate: () => setActionError(""),
    mutationFn: ({ therapy, active }: { therapy: TherapyOption; active: boolean }) => requestJson<TherapyOption>(`/api/commercial/therapies/${therapy.id}`, {
      method: "PATCH", body: JSON.stringify({ is_active: active }),
    }),
    onSuccess: async (therapy) => {
      updateCache(therapy);
      setActionError("");
      setNotice(therapy.is_active ? "Therapy activated successfully." : "Therapy deactivated successfully.");
      setConfirmation(null);
      await refreshPublic();
    },
    onError: (error) => { setActionError(error.message); setConfirmation(null); },
  });

  const remove = useMutation({
    onMutate: () => setActionError(""),
    mutationFn: (therapy: TherapyOption) => requestJson<void>(`/api/commercial/therapies/${therapy.id}`, { method: "DELETE" }),
    onSuccess: async (_, therapy) => {
      queryClient.setQueryData<TherapyOption[]>(["commercial-therapies"], (current) => (current ?? []).filter((item) => item.id !== therapy.id));
      setExpandedId((current) => current === therapy.id ? null : current);
      setActionError("");
      setNotice("Therapy deleted successfully.");
      setConfirmation(null);
      await refreshPublic();
    },
    onError: (error) => { setActionError(error.message); setConfirmation(null); },
  });

  const openAdd = () => {
    slugTouched.current = false;
    setEditing(null);
    setForm(emptyForm());
    setErrors({});
    setNotice("");
    setActionError("");
  };
  const openEdit = (therapy: TherapyOption) => {
    slugTouched.current = true;
    setEditing(therapy);
    setForm({
      name: therapy.name,
      slug: therapy.slug,
      short_description: therapy.short_description ?? "",
      detailed_description: therapy.detailed_description ?? "",
      benefits: (therapy.benefits ?? []).join("\n"),
      base_price: therapy.base_price ?? "0",
      is_publicly_visible: therapy.is_publicly_visible ?? true,
      display_order: therapy.display_order ?? 0,
    });
    setErrors({});
    setNotice("");
    setActionError("");
  };

  return <section id="therapy-management" className="mt-8 space-y-5" aria-labelledby="therapy-management-heading">
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div><p className="text-xs font-bold uppercase tracking-wider text-emerald-700">Therapies &amp; Pricing</p><h2 id="therapy-management-heading" className="text-2xl font-bold">Therapy Management</h2><p className="mt-1 text-slate-600">Manage the authoritative therapy catalogue without changing the customer-facing card layout.</p></div>
      <button type="button" onClick={openAdd} className="min-h-11 rounded-xl bg-emerald-700 px-5 font-bold text-white">+ Add Therapy</button>
    </div>

    {notice && <p role="status" aria-live="polite" className="fixed right-4 top-4 z-50 max-w-sm rounded-xl border border-emerald-200 bg-emerald-50 p-4 font-semibold text-emerald-900 shadow-xl">{notice}</p>}
    {actionError && <p role="alert" className="fixed right-4 top-4 z-50 max-w-sm rounded-xl border border-red-200 bg-red-50 p-4 font-semibold text-red-900 shadow-xl">{actionError}</p>}

    <div className="flex flex-wrap gap-3 rounded-2xl border bg-white p-4">
      <label className="min-w-56 flex-1"><span className="sr-only">Search therapies</span><input aria-label="Search therapies" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search therapies..." className="min-h-11 w-full rounded-xl border px-3" /></label>
      <div className="flex rounded-xl border p-1" aria-label="Therapy status filter">{(["ALL", "ACTIVE", "INACTIVE"] as Filter[]).map((value) => <button key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)} className={`min-h-9 rounded-lg px-3 text-sm font-bold ${filter === value ? "bg-emerald-700 text-white" : "text-slate-600"}`}>{value[0] + value.slice(1).toLowerCase()}</button>)}</div>
    </div>

    <div className="space-y-2">
      {therapies.map((therapy) => {
        const expanded = expandedId === therapy.id;
        const references = Object.entries(therapy.protected_references ?? {}).filter(([, count]) => count > 0);
        return <article key={therapy.id} className="overflow-hidden rounded-2xl border bg-white">
          <div role="button" tabIndex={0} aria-expanded={expanded} onClick={() => setExpandedId(expanded ? null : therapy.id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") setExpandedId(expanded ? null : therapy.id); }} className="grid cursor-pointer items-center gap-3 p-3 sm:grid-cols-[minmax(10rem,1.5fr)_7rem_6rem_6rem_auto]">
            <strong className="min-w-0 truncate text-lg">{therapy.name}</strong>
            <span className="font-semibold text-emerald-800">{money(therapy.base_price)}</span>
            <span className="text-sm text-slate-600">{therapy.default_duration_minutes ?? 45} min</span>
            <span className={`w-fit rounded-full px-2 py-1 text-xs font-bold ${therapy.is_active ? "bg-emerald-50 text-emerald-800" : "bg-slate-100 text-slate-600"}`}>{therapy.is_active ? "Active" : "Inactive"}</span>
            <div className="flex flex-wrap items-center justify-end gap-2" onClick={(event) => event.stopPropagation()}>
              <button type="button" onClick={() => openEdit(therapy)} className="min-h-9 rounded-lg border px-3 text-sm font-bold">Edit</button>
              {therapy.is_active ? therapy.can_delete
                ? <button type="button" onClick={() => setConfirmation({ therapy, action: "DELETE" })} className="min-h-9 rounded-lg bg-red-50 px-3 text-sm font-bold text-red-700">Delete</button>
                : <button type="button" onClick={() => setConfirmation({ therapy, action: "DEACTIVATE" })} className="min-h-9 rounded-lg bg-amber-50 px-3 text-sm font-bold text-amber-800">Deactivate</button>
                : <button type="button" onClick={() => changeStatus.mutate({ therapy, active: true })} disabled={changeStatus.isPending} className="min-h-9 rounded-lg bg-emerald-50 px-3 text-sm font-bold text-emerald-800">Reactivate</button>}
              {!therapy.is_active && therapy.can_delete && <button type="button" onClick={() => setConfirmation({ therapy, action: "DELETE" })} className="min-h-9 rounded-lg bg-red-50 px-3 text-sm font-bold text-red-700">Delete</button>}
              <button type="button" aria-label={expanded ? `Collapse ${therapy.name}` : `Expand ${therapy.name}`} onClick={() => setExpandedId(expanded ? null : therapy.id)} className="min-h-9 min-w-9 rounded-lg border font-bold">{expanded ? "▲" : "▼"}</button>
            </div>
          </div>
          {expanded && <div className="border-t bg-slate-50 p-4">
            <dl className="grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
              <div><dt className="font-bold">Customer-facing description</dt><dd className="mt-1 text-slate-700">{therapy.short_description || "Not provided"}</dd></div>
              <div><dt className="font-bold">Detailed information</dt><dd className="mt-1 whitespace-pre-line text-slate-700">{therapy.detailed_description || "Not provided"}</dd></div>
              <div><dt className="font-bold">Duration and price</dt><dd className="mt-1 text-slate-700">{therapy.default_duration_minutes ?? 45} minutes · {money(therapy.base_price)}</dd></div>
              <div><dt className="font-bold">Customer availability</dt><dd className="mt-1 text-slate-700">{therapy.is_active && therapy.is_publicly_visible ? "Public and bookable" : therapy.is_active ? "Active but hidden from customers" : "Inactive and not bookable"}</dd></div>
              <div className="sm:col-span-2"><dt className="font-bold">Benefits</dt><dd className="mt-1 text-slate-700">{therapy.benefits?.length ? <ul className="list-inside list-disc">{therapy.benefits.map((benefit) => <li key={benefit}>{benefit}</li>)}</ul> : "Not provided"}</dd></div>
              <div><dt className="font-bold">Catalogue order</dt><dd className="mt-1 text-slate-700">{therapy.display_order ?? 0}</dd></div>
              <div><dt className="font-bold">Removal protection</dt><dd className="mt-1 text-slate-700">{therapy.can_delete ? "Unused — safe delete is available" : references.length ? references.map(([name, count]) => `${name.replaceAll("_", " ")}: ${count}`).join(" · ") : "Historical references are protected"}</dd></div>
            </dl>
          </div>}
        </article>;
      })}
      {!query.isPending && therapies.length === 0 && <p className="rounded-2xl border border-dashed bg-white p-6 text-center text-slate-600">No therapies match this search or filter.</p>}
      {query.isPending && <p className="rounded-2xl border bg-white p-5 text-slate-600">Loading therapies…</p>}
      {query.isError && <p role="alert" className="rounded-2xl bg-red-50 p-5 text-red-800">{query.error.message}</p>}
    </div>

    {editing !== undefined && <div role="dialog" aria-modal="true" aria-labelledby="therapy-form-heading" className="fixed inset-0 z-40 grid place-items-center overflow-y-auto bg-slate-950/50 p-4">
      <form noValidate onSubmit={(event) => { event.preventDefault(); if (submitLock.current) return; submitLock.current = true; save.mutate(); }} className="my-6 grid w-full max-w-3xl gap-4 rounded-2xl bg-white p-6 shadow-2xl sm:grid-cols-2">
        <div className="sm:col-span-2"><h3 id="therapy-form-heading" className="text-2xl font-bold">{editing ? `Edit ${editing.name}` : "Add Therapy"}</h3><p className="mt-1 text-sm text-slate-600">Enter the existing catalogue information used by bookings and customer pages.</p></div>
        <label className="grid gap-1 font-semibold">Therapy Name<input aria-label="Therapy Name" value={form.name} onChange={(event) => { const name = event.target.value; setForm((current) => ({ ...current, name, slug: slugTouched.current ? current.slug : slugify(name) })); }} className="min-h-11 rounded-xl border px-3 font-normal" /><ErrorText>{errors.name}</ErrorText></label>
        <label className="grid gap-1 font-semibold">URL Slug<input aria-label="URL Slug" value={form.slug} onChange={(event) => { slugTouched.current = true; setForm({ ...form, slug: slugify(event.target.value) }); }} placeholder="abhyang" className="min-h-11 rounded-xl border px-3 font-normal" /><span className="text-xs font-normal text-slate-500">Lowercase identifier used in customer-facing links.</span><ErrorText>{errors.slug}</ErrorText></label>
        <label className="grid gap-1 font-semibold sm:col-span-2">Customer-facing Description<input aria-label="Customer-facing Description" value={form.short_description} maxLength={240} onChange={(event) => setForm({ ...form, short_description: event.target.value })} className="min-h-11 rounded-xl border px-3 font-normal" /><span className="text-xs font-normal text-slate-500">Short summary shown in the existing customer therapy card.</span><ErrorText>{errors.short_description}</ErrorText></label>
        <label className="grid gap-1 font-semibold sm:col-span-2">Detailed Information<textarea aria-label="Detailed Information" value={form.detailed_description} maxLength={2000} rows={4} onChange={(event) => setForm({ ...form, detailed_description: event.target.value })} className="rounded-xl border p-3 font-normal" /><span className="text-xs font-normal text-slate-500">Use the established backend field for how the therapy is described. Do not add medical claims.</span></label>
        <label className="grid gap-1 font-semibold sm:col-span-2">Benefits<textarea aria-label="Benefits" value={form.benefits} rows={3} onChange={(event) => setForm({ ...form, benefits: event.target.value })} placeholder={"One benefit per line"} className="rounded-xl border p-3 font-normal" /><span className="text-xs font-normal text-slate-500">One existing customer-facing benefit per line.</span></label>
        <label className="grid gap-1 font-semibold">Price (₹)<input aria-label="Price (₹)" type="number" min="0" step="0.01" value={form.base_price} onChange={(event) => setForm({ ...form, base_price: event.target.value })} className="min-h-11 rounded-xl border px-3 font-normal" /><ErrorText>{errors.base_price}</ErrorText></label>
        <label className="grid gap-1 font-semibold">Duration<input aria-label="Duration" value="45 minutes" disabled className="min-h-11 rounded-xl border bg-slate-100 px-3 font-normal" /><span className="text-xs font-normal text-slate-500">Production scheduling currently uses exactly 45 minutes per therapy.</span></label>
        <label className="grid gap-1 font-semibold">Catalogue Order<input aria-label="Catalogue Order" type="number" min="0" value={form.display_order} onChange={(event) => setForm({ ...form, display_order: Number(event.target.value) })} className="min-h-11 rounded-xl border px-3 font-normal" /></label>
        <label className="flex items-center gap-2 self-center font-semibold"><input type="checkbox" checked={form.is_publicly_visible} onChange={(event) => setForm({ ...form, is_publicly_visible: event.target.checked })} /> Public and bookable when active</label>
        {errors.form && <p role="alert" className="rounded-xl bg-red-50 p-3 text-red-800 sm:col-span-2">{errors.form}</p>}
        <div className="flex justify-end gap-3 sm:col-span-2"><button type="button" onClick={() => { setEditing(undefined); setErrors({}); }} className="min-h-11 rounded-xl border px-5 font-bold">Cancel</button><button disabled={save.isPending} className="min-h-11 rounded-xl bg-emerald-700 px-5 font-bold text-white disabled:opacity-60">{save.isPending ? "Saving..." : editing ? "Save Changes" : "Add Therapy"}</button></div>
      </form>
    </div>}

    {confirmation && <div role="dialog" aria-modal="true" aria-labelledby="therapy-confirm-heading" className="fixed inset-0 z-50 grid place-items-center bg-slate-950/50 p-4"><div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl"><h3 id="therapy-confirm-heading" className="text-xl font-bold">{confirmation.action === "DELETE" ? `Delete ${confirmation.therapy.name}?` : `Deactivate ${confirmation.therapy.name}?`}</h3><p className="mt-3 text-slate-700">{confirmation.action === "DELETE" ? "The backend confirms this therapy has never been used. This permanent action cannot be undone." : "Customers will no longer be able to make new bookings for this therapy. Existing historical appointments and records will remain unchanged."}</p><div className="mt-5 flex justify-end gap-3"><button type="button" onClick={() => setConfirmation(null)} className="min-h-11 rounded-xl border px-5 font-bold">Cancel</button><button type="button" disabled={changeStatus.isPending || remove.isPending} onClick={() => confirmation.action === "DELETE" ? remove.mutate(confirmation.therapy) : changeStatus.mutate({ therapy: confirmation.therapy, active: false })} className="min-h-11 rounded-xl bg-red-700 px-5 font-bold text-white">{changeStatus.isPending || remove.isPending ? "Saving..." : confirmation.action === "DELETE" ? "Delete" : "Deactivate"}</button></div></div></div>}
  </section>;
}
