"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { requestJson } from "@/lib/api/client";
import type {
  AppointmentAuditEvent,
  OperationalAppointment,
  OperationalAppointmentPage,
  TherapyOption,
} from "@/lib/appointments/contracts";
import type { PatientPage } from "@/lib/patients/contracts";
import type { StaffPage } from "@/lib/staff/contracts";

type Session = {
  access: {
    permitted_clinics: Array<{ id: string; slug: string }>;
    roles: Array<{ role: string }>;
  };
};

type Filters = { clinic: string; date: string; status: string; therapy: string; physiotherapist: string };
const initialFilters: Filters = { clinic: "", date: "", status: "", therapy: "", physiotherapist: "" };
const editableStatuses = ["DRAFT", "PENDING_ASSIGNMENT", "SCHEDULED", "CONFIRMED"];
const cancellationCategories = [
  ["CUSTOMER_REQUEST", "Customer request"],
  ["PHYSIOTHERAPIST_UNAVAILABLE", "Physiotherapist unavailable"],
  ["CLINIC_OPERATIONAL_ISSUE", "Clinic operational issue"],
  ["SCHEDULING_CONFLICT", "Scheduling conflict"],
  ["DUPLICATE_APPOINTMENT", "Duplicate appointment"],
  ["OTHER", "Other"],
];

function queryString(filters: Filters) {
  const query = new URLSearchParams();
  if (filters.clinic) query.set("clinic", filters.clinic);
  if (filters.date) {
    query.set("date_from", filters.date);
    query.set("date_to", filters.date);
  }
  if (filters.status) query.set("status", filters.status);
  if (filters.therapy) query.set("therapy", filters.therapy);
  if (filters.physiotherapist) query.set("physiotherapist", filters.physiotherapist);
  return query.toString();
}

export function ScheduleOperations() {
  const [showForm, setShowForm] = useState(false);
  const [filters, setFilters] = useState(initialFilters);
  const [assignments, setAssignments] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<OperationalAppointment | null>(null);
  const [action, setAction] = useState<"reschedule" | "cancel" | "audit" | null>(null);
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["schedule-operations", filters],
    queryFn: () => requestJson<OperationalAppointmentPage>(`/api/schedule/operations?${queryString(filters)}`),
  });
  const patients = useQuery({ queryKey: ["schedule-patients"], queryFn: () => requestJson<PatientPage>("/api/patients?status=active&page_size=50") });
  const staff = useQuery({ queryKey: ["schedule-staff"], queryFn: () => requestJson<StaffPage>("/api/staff/profiles?type=PHYSIOTHERAPIST&status=active&page_size=50") });
  const therapies = useQuery({ queryKey: ["schedule-therapies"], queryFn: () => requestJson<TherapyOption[]>("/api/appointment-therapies") });
  const session = useQuery({ queryKey: ["schedule-session"], queryFn: () => requestJson<Session>("/api/session/me") });
  const isOwner = session.data?.access.roles?.some((role) => role.role === "OWNER") ?? false;
  const invalidate = () => client.invalidateQueries({ queryKey: ["schedule-operations"] });
  const create = useMutation({
    mutationFn: (value: Record<string, unknown>) => {
      const requestId = String(value.request_id ?? "");
      const payload = { ...value };
      delete payload.request_id;
      return requestJson(requestId ? `/api/schedule/convert/${requestId}` : "/api/schedule", { method: "POST", body: JSON.stringify(payload) });
    },
    onSuccess: () => { setShowForm(false); invalidate(); },
  });
  const transition = useMutation({ mutationFn: ({ id, next }: { id: string; next: string }) => requestJson(`/api/schedule/${id}/status`, { method: "POST", body: JSON.stringify({ status: next, reason: "Updated by authorized operations staff." }) }), onSuccess: invalidate });
  const assign = useMutation({ mutationFn: ({ id, physiotherapist }: { id: string; physiotherapist: string }) => requestJson(`/api/schedule/${id}/assign`, { method: "POST", body: JSON.stringify({ physiotherapist, reason: "Assignment updated by authorized operations staff." }) }), onSuccess: invalidate });
  const reschedule = useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) => requestJson(`/api/schedule/${id}/reschedule`, { method: "POST", body: JSON.stringify(payload) }), onSuccess: () => { setAction(null); invalidate(); } });
  const cancel = useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) => requestJson(`/api/schedule/${id}/cancel`, { method: "POST", body: JSON.stringify(payload) }), onSuccess: () => { setAction(null); invalidate(); } });
  const audit = useQuery({
    queryKey: ["appointment-audit", selected?.id],
    queryFn: () => requestJson<{ results: AppointmentAuditEvent[] }>(`/api/schedule/${selected?.id}/audit`),
    enabled: Boolean(selected && action === "audit"),
  });

  function submitCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    create.mutate({ request_id: data.get("request_id"), patient: data.get("patient"), therapy: data.get("therapy"), clinic: data.get("clinic"), physiotherapist: data.get("physiotherapist") || null, scheduled_start: data.get("scheduled_start"), status: data.get("status"), address_line_1: data.get("address_line_1"), address_line_2: "", landmark: data.get("landmark"), city: data.get("city"), region: data.get("region"), pin_code: data.get("pin_code"), operational_notes: data.get("operational_notes") });
  }

  function submitReschedule(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const data = new FormData(event.currentTarget);
    reschedule.mutate({ id: selected.id, payload: { scheduled_start: data.get("scheduled_start"), duration_minutes: Number(data.get("duration_minutes")), override: data.get("override") === "on", override_reason: data.get("override_reason") } });
  }

  function submitCancellation(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const data = new FormData(event.currentTarget);
    cancel.mutate({ id: selected.id, payload: { reason_category: data.get("reason_category"), operational_reason: data.get("operational_reason"), override: data.get("override") === "on", override_reason: data.get("override_reason") } });
  }

  return <section className="mt-8" aria-labelledby="schedule-heading">
    <div className="flex flex-wrap items-end justify-between gap-3"><div><h2 id="schedule-heading" className="text-2xl font-bold">Appointment operations</h2><p className="text-slate-600">Responsive clinic calendar, queue, assignment, and lifecycle controls.</p></div><button onClick={() => setShowForm((value) => !value)} className="min-h-11 rounded-xl bg-emerald-700 px-4 font-bold text-white">{showForm ? "Close form" : "Create appointment"}</button></div>
    {showForm && <form aria-label="Create operational appointment" onSubmit={submitCreate} className="mt-5 grid gap-4 rounded-2xl border bg-white p-5 sm:grid-cols-2"><Field name="request_id" label="Approved request ID (optional conversion)" required={false}/><Select name="patient" label="Patient" options={patients.data?.results.map((patient) => [patient.id, `${patient.patient_identifier} · ${patient.full_name}`])}/><Select name="therapy" label="Therapy" options={therapies.data?.map((therapy) => [therapy.id, therapy.name])}/><Select name="clinic" label="Clinic" options={session.data?.access.permitted_clinics.map((clinic) => [clinic.id, clinic.slug])}/><Select name="physiotherapist" label="Physiotherapist (optional for draft)" required={false} options={staff.data?.results.map((profile) => [profile.id, profile.full_name])}/><Field name="scheduled_start" label="Start date and time" type="datetime-local"/><label className="grid gap-1 font-semibold">Initial status<select name="status" className="min-h-11 rounded-xl border px-3"><option value="DRAFT">Draft</option><option value="PENDING_ASSIGNMENT">Pending assignment</option><option value="SCHEDULED">Scheduled</option></select></label><Field name="address_line_1" label="Service address"/><Field name="landmark" label="Landmark" required={false}/><Field name="city" label="City"/><Field name="region" label="State"/><Field name="pin_code" label="PIN code"/><Field name="operational_notes" label="Short non-clinical operational note" required={false}/><button disabled={create.isPending} className="min-h-11 rounded-xl bg-emerald-700 font-bold text-white sm:col-span-2">{create.isPending ? "Creating…" : "Create appointment"}</button>{create.isError && <p role="alert" className="text-red-700 sm:col-span-2">{create.error.message}</p>}</form>}
    <div aria-label="Appointment filters" className="mt-5 grid gap-3 rounded-2xl border bg-white p-4 sm:grid-cols-2 xl:grid-cols-5"><Select name="clinic-filter" label="Clinic" required={false} value={filters.clinic} onChange={(value) => setFilters({ ...filters, clinic: value })} options={session.data?.access.permitted_clinics.map((clinic) => [clinic.id, clinic.slug])}/><Field name="date-filter" label="Date" type="date" required={false} value={filters.date} onChange={(value) => setFilters({ ...filters, date: value })}/><Select name="status-filter" label="Status" required={false} value={filters.status} onChange={(value) => setFilters({ ...filters, status: value })} options={["DRAFT", "PENDING_ASSIGNMENT", "SCHEDULED", "CONFIRMED", "IN_PROGRESS", "COMPLETED", "CANCELLED", "NO_SHOW"].map((status) => [status, status])}/><Select name="therapy-filter" label="Therapy" required={false} value={filters.therapy} onChange={(value) => setFilters({ ...filters, therapy: value })} options={therapies.data?.map((therapy) => [therapy.id, therapy.name])}/><Select name="physiotherapist-filter" label="Physiotherapist" required={false} value={filters.physiotherapist} onChange={(value) => setFilters({ ...filters, physiotherapist: value })} options={staff.data?.results.map((profile) => [profile.id, profile.full_name])}/></div>
    <AppointmentTable items={query.data?.results ?? []} onStatus={(id, next) => transition.mutate({ id, next })} staffOptions={staff.data?.results.map((profile) => [profile.id, profile.full_name])} assignments={assignments} onAssignmentChange={(id, value) => setAssignments((current) => ({ ...current, [id]: value }))} onAssign={(id) => assignments[id] && assign.mutate({ id, physiotherapist: assignments[id] })} onAction={(item, nextAction) => { setSelected(item); setAction(nextAction); }}/>
    {selected && action === "reschedule" && <LifecyclePanel title="Reschedule appointment" onClose={() => setAction(null)}><form onSubmit={submitReschedule} className="grid gap-4 sm:grid-cols-2"><Field name="scheduled_start" label="New date and time" type="datetime-local"/><Field name="duration_minutes" label="Duration in minutes" type="number" defaultValue={String(selected.duration_minutes)}/>{isOwner && <OverrideFields/>}<SubmitAction pending={reschedule.isPending} label="Confirm reschedule" error={reschedule.error?.message}/></form></LifecyclePanel>}
    {selected && action === "cancel" && <LifecyclePanel title="Cancel appointment" onClose={() => setAction(null)}><form onSubmit={submitCancellation} className="grid gap-4 sm:grid-cols-2"><Select name="reason_category" label="Reason category" options={cancellationCategories}/><Field name="operational_reason" label="Short operational reason"/>{isOwner && <OverrideFields/>}<SubmitAction pending={cancel.isPending} label="Confirm cancellation" error={cancel.error?.message}/></form></LifecyclePanel>}
    {selected && action === "audit" && <LifecyclePanel title="Appointment audit timeline" onClose={() => setAction(null)}><ol className="grid gap-3">{audit.data?.results.map((event) => <li key={event.id} className="rounded-xl border p-3"><strong>{event.event} · {event.outcome}</strong><p className="text-sm text-slate-600">{new Date(event.created_at).toLocaleString()} · {event.actor_name}</p>{event.rejection_code && <p className="text-sm">Policy result: {event.rejection_code}</p>}{event.reason_category && <p className="text-sm">Category: {event.reason_category}</p>}{event.override_used && <p className="text-sm font-semibold">Owner override audited</p>}</li>)}</ol></LifecyclePanel>}
  </section>;
}

export function AssignedAppointments() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["assigned-appointments"], queryFn: () => requestJson<OperationalAppointment[]>("/api/schedule/assigned-to-me") });
  const transition = useMutation({ mutationFn: ({ id, next }: { id: string; next: string }) => requestJson(`/api/schedule/${id}/status`, { method: "POST", body: JSON.stringify({ status: next }) }), onSuccess: () => client.invalidateQueries({ queryKey: ["assigned-appointments"] }) });
  return <section className="mt-8"><h2 className="text-2xl font-bold">My assigned appointments</h2><AppointmentTable items={query.data ?? []} onStatus={(id, next) => transition.mutate({ id, next })} physiotherapist/></section>;
}

export function CustomerAppointments() {
  const query = useQuery({ queryKey: ["customer-appointments"], queryFn: () => requestJson<OperationalAppointment[]>("/api/schedule/my-appointments") });
  return <section className="mt-8"><h2 className="text-2xl font-bold">My scheduled appointments</h2><div className="mt-4 grid gap-4 sm:grid-cols-2">{query.data?.map((item) => <article key={item.id} className="rounded-2xl border bg-white p-5">{item.physiotherapist_photo_url && <img src={`/api/schedule/${item.id}/physiotherapist-photo`} alt={`${item.physiotherapist_name} profile`} className="mb-3 size-16 rounded-full object-cover"/>}<h3 className="font-bold">{item.therapy_name}</h3><p>{new Date(item.scheduled_start).toLocaleString()} · {item.status}</p><p className="text-slate-600">{item.address_line_1}, {item.city} {item.pin_code}</p><p>Physiotherapist: {item.physiotherapist_name ?? "Pending assignment"}</p>{item.status === "CANCELLED" && item.cancellation_category && <p className="mt-2 font-semibold">Cancellation: {cancellationCategories.find(([value]) => value === item.cancellation_category)?.[1]}</p>}</article>)}</div></section>;
}

function AppointmentTable({ items, onStatus, physiotherapist = false, staffOptions, assignments, onAssignmentChange, onAssign, onAction }: { items: OperationalAppointment[]; onStatus: (id: string, next: string) => void; physiotherapist?: boolean; staffOptions?: string[][]; assignments?: Record<string, string>; onAssignmentChange?: (id: string, value: string) => void; onAssign?: (id: string) => void; onAction?: (item: OperationalAppointment, action: "reschedule" | "cancel" | "audit") => void }) {
  return <div className="mt-5 overflow-x-auto rounded-2xl border bg-white"><table className="min-w-full text-left text-sm"><thead><tr>{["Patient", "Therapy", "Schedule", "Physiotherapist", "Status", "Actions"].map((heading) => <th className="p-4" key={heading}>{heading}</th>)}</tr></thead><tbody>{items.map((item) => <tr className="border-t" key={item.id}><td className="p-4">{item.patient_name}<span className="block text-slate-500">{item.patient_identifier}</span></td><td className="p-4">{item.therapy_name}</td><td className="p-4">{new Date(item.scheduled_start).toLocaleString()}</td><td className="p-4">{item.physiotherapist_name ?? "Unassigned"}{!physiotherapist && <span className="mt-2 flex gap-2"><select aria-label={`Assign ${item.patient_name}`} value={assignments?.[item.id] ?? ""} onChange={(event) => onAssignmentChange?.(item.id, event.target.value)} className="rounded-lg border px-2"><option value="">Select</option>{staffOptions?.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select><button type="button" className="font-bold underline" onClick={() => onAssign?.(item.id)}>Assign</button></span>}</td><td className="p-4">{item.status}</td><td className="p-4"><div className="flex flex-wrap gap-2">{physiotherapist && item.status === "CONFIRMED" && <><button className="font-bold underline" onClick={() => onStatus(item.id, "IN_PROGRESS")}>Start</button><button className="font-bold underline" onClick={() => onStatus(item.id, "NO_SHOW")}>No show</button></>}{physiotherapist && item.status === "IN_PROGRESS" && <button className="font-bold underline" onClick={() => onStatus(item.id, "COMPLETED")}>Complete</button>}{!physiotherapist && item.status === "SCHEDULED" && <button className="font-bold underline" onClick={() => onStatus(item.id, "CONFIRMED")}>Confirm</button>}{!physiotherapist && editableStatuses.includes(item.status) && <><button className="font-bold underline" onClick={() => onAction?.(item, "reschedule")}>Reschedule</button><button className="font-bold text-red-700 underline" onClick={() => onAction?.(item, "cancel")}>Cancel</button></>} {!physiotherapist && <button className="font-bold underline" onClick={() => onAction?.(item, "audit")}>Audit</button>}</div></td></tr>)}</tbody></table>{items.length === 0 && <p className="p-5 text-slate-600">No appointments found.</p>}</div>;
}

function LifecyclePanel({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) { return <aside aria-label={title} className="mt-5 rounded-2xl border border-emerald-200 bg-emerald-50 p-5"><div className="mb-4 flex justify-between"><h3 className="text-xl font-bold">{title}</h3><button onClick={onClose} className="font-bold underline">Close</button></div>{children}</aside>; }
function OverrideFields() { return <><label className="flex min-h-11 items-center gap-2 font-semibold"><input name="override" type="checkbox"/>Owner policy override</label><Field name="override_reason" label="Structured override reason" required={false}/></>; }
function SubmitAction({ pending, label, error }: { pending: boolean; label: string; error?: string }) { return <><button disabled={pending} className="min-h-11 rounded-xl bg-emerald-700 px-4 font-bold text-white sm:col-span-2">{pending ? "Saving…" : label}</button>{error && <p role="alert" className="text-red-700 sm:col-span-2">{error}</p>}</>; }
function Field({ name, label, type = "text", required = true, value, defaultValue, onChange }: { name: string; label: string; type?: string; required?: boolean; value?: string; defaultValue?: string; onChange?: (value: string) => void }) { return <label className="grid gap-1 font-semibold">{label}<input name={name} type={type} required={required} value={value} defaultValue={defaultValue} onChange={onChange ? (event) => onChange(event.target.value) : undefined} min={type === "number" ? 30 : undefined} max={type === "number" ? 180 : undefined} className="min-h-11 rounded-xl border px-3"/></label>; }
function Select({ name, label, options, required = true, value, onChange }: { name: string; label: string; options?: string[][]; required?: boolean; value?: string; onChange?: (value: string) => void }) { return <label className="grid gap-1 font-semibold">{label}<select name={name} required={required} value={value} onChange={onChange ? (event) => onChange(event.target.value) : undefined} className="min-h-11 rounded-xl border px-3"><option value="">Select</option>{options?.map(([optionValue, text]) => <option key={optionValue} value={optionValue}>{text}</option>)}</select></label>; }
