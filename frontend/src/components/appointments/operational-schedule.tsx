"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { requestJson } from "@/lib/api/client";
import { OwnerAppointmentTable } from "@/components/appointments/owner-appointment-table";
import type {
  AppointmentAuditEvent,
  OperationalAppointment,
  OperationalAppointmentPage,
  PhysiotherapistWorkload,
  TherapyOption,
} from "@/lib/appointments/contracts";
import type { StaffPage } from "@/lib/staff/contracts";

type Session = {
  access: {
    permitted_clinics: Array<{ id: string; slug: string }>;
    roles: Array<{ role: string }>;
  };
};

type Filters = { search: string; view: string; clinic: string; date: string; status: string; therapy: string; physiotherapist: string; sort:string };
const initialFilters: Filters = { search: "", view: "", clinic: "", date: "", status: "", therapy: "", physiotherapist: "", sort:"scheduled_start" };
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
  if (filters.search) query.set("search", filters.search);
  if (filters.view) query.set("view", filters.view);
  if (filters.clinic) query.set("clinic", filters.clinic);
  if (filters.date) {
    query.set("date_from", filters.date);
    query.set("date_to", filters.date);
  }
  if (filters.status) query.set("status", filters.status);
  if (filters.therapy) query.set("therapy", filters.therapy);
  if (filters.physiotherapist) query.set("physiotherapist", filters.physiotherapist);
  query.set("ordering", filters.sort);
  return query.toString();
}

export function ScheduleOperations() {
  const [filters, setFilters] = useState(initialFilters);
  const [assignments, setAssignments] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<OperationalAppointment | null>(null);
  const [action, setAction] = useState<"detail" | "reschedule" | "cancel" | "audit" | null>(null);
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["schedule-operations", filters],
    queryFn: () => requestJson<OperationalAppointmentPage>(`/api/schedule/operations?${queryString(filters)}`), refetchInterval: 15_000,
  });
  const staff = useQuery({ queryKey: ["schedule-staff"], queryFn: () => requestJson<StaffPage>("/api/staff/profiles?type=PHYSIOTHERAPIST&status=active&page_size=50") });
  const therapies = useQuery({ queryKey: ["schedule-therapies"], queryFn: () => requestJson<TherapyOption[]>("/api/appointment-therapies") });
  const session = useQuery({ queryKey: ["schedule-session"], queryFn: () => requestJson<Session>("/api/session/me") });
  const workload = useQuery({ queryKey: ["physiotherapist-workload"], queryFn: () => requestJson<PhysiotherapistWorkload[]>("/api/schedule/physiotherapist-workload") });
  const isOwner = session.data?.access.roles?.some((role) => role.role === "OWNER") ?? false;
  const invalidate = () => client.invalidateQueries({ queryKey: ["schedule-operations"] });
  const transition = useMutation({ mutationFn: ({ id, next }: { id: string; next: string }) => requestJson(`/api/schedule/${id}/status`, { method: "POST", body: JSON.stringify({ status: next, reason: "Updated by authorized operations staff." }) }), onSuccess: invalidate });
  const assign = useMutation({ mutationFn: ({ id, physiotherapist }: { id: string; physiotherapist: string }) => requestJson(`/api/schedule/${id}/assign`, { method: "POST", body: JSON.stringify({ physiotherapist, reason: "Assignment updated by authorized operations staff." }) }), onSuccess: invalidate });
  const unassign = useMutation({ mutationFn: (id: string) => requestJson(`/api/schedule/${id}/unassign`, { method: "POST", body: JSON.stringify({ reason: "Assignment cancelled by authorized dispatch staff." }) }), onSuccess: invalidate });
  const reschedule = useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) => requestJson(`/api/schedule/${id}/reschedule`, { method: "POST", body: JSON.stringify(payload) }), onSuccess: () => { setAction(null); invalidate(); } });
  const cancel = useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) => requestJson(`/api/schedule/${id}/cancel`, { method: "POST", body: JSON.stringify(payload) }), onSuccess: () => { setAction(null); invalidate(); } });
  const audit = useQuery({
    queryKey: ["appointment-audit", selected?.id],
    queryFn: () => requestJson<{ results: AppointmentAuditEvent[] }>(`/api/schedule/${selected?.id}/audit`),
    enabled: Boolean(selected && action === "audit"),
  });

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
    <div><h1 id="schedule-heading" className="text-3xl font-bold">Appointment Schedule</h1><p className="text-slate-600">Search, filter and manage canonical appointments.</p></div>
    <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Physiotherapist workload">{workload.data?.map((item) => <article key={item.id} className="rounded-2xl border bg-white p-4"><strong>{item.full_name}</strong><p className="text-sm text-slate-600">{item.clinic}</p><p>{item.active_assignments} active · {item.upcoming_assignments} upcoming</p></article>)}</div>
    <div className="mt-6 rounded-2xl border bg-slate-50 p-4 sm:p-5"><h2 className="text-2xl font-bold">Search Appointments</h2><p className="text-sm text-slate-600">Search by customer, mobile number or booking reference, then refine the results.</p><div aria-label="Appointment filters" className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Field name="search-filter" label="Search customer / mobile / booking reference" required={false} value={filters.search} onChange={(value) => setFilters({ ...filters, search: value })}/><Select name="view-filter" label="View" required={false} value={filters.view} onChange={(value) => setFilters({ ...filters, view: value })} options={[["today", "Today"], ["upcoming", "Upcoming"], ["completed", "Completed"], ["cancelled", "Cancelled"]]}/><Select name="status-filter" label="Status" required={false} value={filters.status} onChange={(value) => setFilters({ ...filters, status: value })} options={["DRAFT", "PENDING_ASSIGNMENT", "SCHEDULED", "CONFIRMED", "IN_PROGRESS", "COMPLETED", "CANCELLED", "NO_SHOW"].map((status) => [status, status])}/><Select name="therapy-filter" label="Therapy" required={false} value={filters.therapy} onChange={(value) => setFilters({ ...filters, therapy: value })} options={therapies.data?.map((therapy) => [therapy.id, therapy.name])}/><Select name="physiotherapist-filter" label="Therapist" required={false} value={filters.physiotherapist} onChange={(value) => setFilters({ ...filters, physiotherapist: value })} options={staff.data?.results.map((profile) => [profile.id, profile.full_name])}/><Field name="date-filter" label="Date" type="date" required={false} value={filters.date} onChange={(value) => setFilters({ ...filters, date: value })}/><Select name="clinic-filter" label="Clinic" required={false} value={filters.clinic} onChange={(value) => setFilters({ ...filters, clinic: value })} options={session.data?.access.permitted_clinics.map((clinic) => [clinic.id, clinic.slug])}/></div>
    <div className="mt-3 max-w-xs"><Select name="sort-filter" label="Sort" value={filters.sort} onChange={(value) => setFilters({...filters,sort:value})} options={[["scheduled_start","Date: earliest first"],["-scheduled_start","Date: latest first"],["-created_at","Newest created first"]]}/></div>
    <OwnerAppointmentTable items={query.data?.results ?? []} onStatus={(id, next) => transition.mutate({ id, next })} staffOptions={staff.data?.results.map((profile) => [profile.id, profile.full_name])} assignments={assignments} onAssignmentChange={(id, value) => setAssignments((current) => ({ ...current, [id]: value }))} onAssign={(id) => assignments[id] && assign.mutate({ id, physiotherapist: assignments[id] })} onUnassign={(id) => unassign.mutate(id)} onAction={(item, nextAction) => { setSelected(item); setAction(nextAction); }}/></div>
    {selected && action === "detail" && <LifecyclePanel title="Appointment details" onClose={() => setAction(null)}><dl className="grid gap-3 text-sm sm:grid-cols-2"><Detail label="Appointment reference" value={selected.id}/><Detail label="Customer request reference" value={selected.originating_request || "Direct operational appointment"}/><Detail label="Customer" value={`${selected.patient_name} (${selected.patient_identifier})`}/><Detail label="Therapies" value={(selected.requested_therapy_names?.length ? selected.requested_therapy_names : [selected.therapy_name]).join(", ")}/><Detail label="Start" value={new Date(selected.scheduled_start).toLocaleString()}/><Detail label="End" value={new Date(selected.scheduled_end).toLocaleString()}/><Detail label="Duration" value={`${selected.duration_minutes} minutes`}/><Detail label="Service address snapshot" value={[selected.address_line_1,selected.address_line_2,selected.landmark,selected.city,selected.region,selected.pin_code].filter(Boolean).join(", ")}/><Detail label="Therapist" value={selected.physiotherapist_name || "Unassigned"}/><Detail label="Appointment status" value={selected.status === "COMPLETED" ? "Appointment completed successfully" : selected.status}/><Detail label="Assignment status" value={selected.assignment_status === "REJECTED" ? "Reassignment required" : selected.assignment_status}/>{selected.service_started_at&&<Detail label="Session started" value={new Date(selected.service_started_at).toLocaleString()}/>} {selected.completed_at&&<Detail label="Treatment completed" value={new Date(selected.completed_at).toLocaleString()}/>} {selected.status==="COMPLETED"&&<Detail label="Amount due" value={selected.payment_amount_due?`₹${selected.payment_amount_due}`:"Amount unavailable"}/>} {selected.status==="COMPLETED"&&<Detail label="Payment" value={selected.payment_status==="PAID"?"Payment confirmed":"Payment pending"}/>} {selected.payment_paid_at&&<Detail label="Payment confirmed at" value={new Date(selected.payment_paid_at).toLocaleString()}/>} {selected.payment_confirmed_by&&<Detail label="Payment confirmed by" value={selected.payment_confirmed_by}/>} {selected.manager_remarks&&<Detail label="Customer-visible note" value={selected.manager_remarks}/>}</dl></LifecyclePanel>}
    {selected && action === "reschedule" && <LifecyclePanel title="Reschedule appointment" onClose={() => setAction(null)}><form onSubmit={submitReschedule} className="grid gap-4 sm:grid-cols-2"><Field name="scheduled_start" label="New date and time" type="datetime-local"/><Field name="duration_minutes" label="Duration in minutes" type="number" defaultValue={String(selected.duration_minutes)}/>{isOwner && <OverrideFields/>}<SubmitAction pending={reschedule.isPending} label="Confirm reschedule" error={reschedule.error?.message}/></form></LifecyclePanel>}
    {selected && action === "cancel" && <LifecyclePanel title="Cancel appointment" onClose={() => setAction(null)}><form onSubmit={submitCancellation} className="grid gap-4 sm:grid-cols-2"><Select name="reason_category" label="Reason category" options={cancellationCategories}/><Field name="operational_reason" label="Short operational reason"/>{isOwner && <OverrideFields/>}<SubmitAction pending={cancel.isPending} label="Confirm cancellation" error={cancel.error?.message}/></form></LifecyclePanel>}
    {selected && action === "audit" && <LifecyclePanel title="Appointment audit timeline" onClose={() => setAction(null)}><ol className="grid gap-3">{audit.data?.results.map((event) => <li key={event.id} className="rounded-xl border p-3"><strong>{event.event} · {event.outcome}</strong><p className="text-sm text-slate-600">{new Date(event.created_at).toLocaleString()} · {event.actor_name}</p>{event.rejection_code && <p className="text-sm">Policy result: {event.rejection_code}</p>}{event.reason_category && <p className="text-sm">Category: {event.reason_category}</p>}{event.override_used && <p className="text-sm font-semibold">Owner override audited</p>}</li>)}</ol></LifecyclePanel>}
  </section>;
}

export function AssignedAppointments() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["assigned-appointments"], queryFn: () => requestJson<OperationalAppointment[]>("/api/schedule/assigned-to-me") });
  const transition = useMutation({ mutationFn: ({ id, next }: { id: string; next: string }) => requestJson(`/api/schedule/${id}/status`, { method: "POST", body: JSON.stringify({ status: next }) }), onSuccess: () => client.invalidateQueries({ queryKey: ["assigned-appointments"] }) });
  const respond = useMutation({ mutationFn: ({ id, accept, reason }: { id: string; accept: boolean; reason?: string }) => requestJson(`/api/schedule/${id}/assignment-response`, { method: "POST", body: JSON.stringify({ accept, reason }) }), onSuccess: () => client.invalidateQueries({ queryKey: ["assigned-appointments"] }) });
  const today = new Date().toDateString();
  const todayItems = query.data?.filter((item) => new Date(item.scheduled_start).toDateString() === today) ?? [];
  const upcomingItems = query.data?.filter((item) => new Date(item.scheduled_start).toDateString() !== today && new Date(item.scheduled_start) > new Date()) ?? [];
  const table = (items: OperationalAppointment[]) => <AppointmentTable items={items} onStatus={(id, next) => transition.mutate({ id, next })} onAssignmentResponse={(id, accept, reason) => respond.mutate({ id, accept, reason })} physiotherapist/>;
  return <section className="mt-8"><h2 className="text-2xl font-bold">My assigned appointments</h2><p className="text-slate-600">Review assigned patients and home visits.</p><h3 className="mt-5 text-xl font-bold">Today&apos;s appointments</h3>{table(todayItems)}<h3 className="mt-7 text-xl font-bold">Upcoming appointments</h3>{table(upcomingItems)}</section>;
}

export function CustomerAppointments() {
  const query = useQuery({ queryKey: ["customer-appointments"], queryFn: () => requestJson<OperationalAppointment[]>("/api/schedule/my-appointments") });
  const client = useQueryClient();
  const change = useMutation({ mutationFn: ({ id, kind, reason, requested_start }: { id: string; kind: "RESCHEDULE" | "CANCELLATION"; reason: string; requested_start?: string }) => requestJson(`/api/schedule/my-appointments/${id}/change-requests`, { method: "POST", body: JSON.stringify({ kind, reason, requested_start: requested_start || null }) }), onSuccess: () => client.invalidateQueries({ queryKey: ["customer-appointments"] }) });
  function requestChange(event: React.FormEvent<HTMLFormElement>, id: string, kind: "RESCHEDULE" | "CANCELLATION") { event.preventDefault(); const data = new FormData(event.currentTarget); change.mutate({ id, kind, reason: String(data.get("reason")), requested_start: String(data.get("requested_start") || "") }); }
  return <section className="mt-8"><h2 className="text-2xl font-bold">My scheduled appointments</h2><div className="mt-4 grid gap-4 sm:grid-cols-2">{query.data?.map((item) => <article key={item.id} className="rounded-2xl border bg-white p-5">{item.physiotherapist_photo_url && <img src={`/api/schedule/${item.id}/physiotherapist-photo`} alt={`${item.physiotherapist_name} profile`} className="mb-3 size-16 rounded-full object-cover"/>}<h3 className="font-bold">{item.therapy_name}</h3><p>{new Date(item.scheduled_start).toLocaleString()} Â· {item.status}</p><p className="text-slate-600">{item.address_line_1}, {item.city} {item.pin_code}</p><p>Physiotherapist: {item.physiotherapist_name ?? "Pending assignment"}</p>{item.physiotherapist_name && <p className="text-sm">{item.physiotherapist_qualification} Â· {item.physiotherapist_experience_years ?? 0} years experience</p>}{item.manager_remarks && <p className="mt-2">Manager remarks: {item.manager_remarks}</p>}<div className="mt-4 grid gap-3"><form aria-label={`Request reschedule for ${item.therapy_name}`} onSubmit={(event) => requestChange(event, item.id, "RESCHEDULE")} className="grid gap-2 rounded-xl bg-slate-50 p-3"><Field name="requested_start" label="Preferred new date and time" type="datetime-local"/><Field name="reason" label="Reschedule reason"/><button className="min-h-11 rounded-xl border px-3 font-semibold">Request reschedule</button></form><form aria-label={`Request cancellation for ${item.therapy_name}`} onSubmit={(event) => requestChange(event, item.id, "CANCELLATION")} className="grid gap-2 rounded-xl bg-slate-50 p-3"><Field name="reason" label="Cancellation reason"/><button className="min-h-11 rounded-xl border border-red-200 px-3 font-semibold text-red-700">Request cancellation</button></form></div>{item.status === "CANCELLED" && item.cancellation_category && <p className="mt-2 font-semibold">Cancellation: {cancellationCategories.find(([value]) => value === item.cancellation_category)?.[1]}</p>}</article>)}</div></section>;
}

function AppointmentTable({ items, onStatus, physiotherapist = false, staffOptions, assignments, onAssignmentChange, onAssign, onUnassign, onAssignmentResponse, onAction }: { items: OperationalAppointment[]; onStatus: (id: string, next: string) => void; physiotherapist?: boolean; staffOptions?: string[][]; assignments?: Record<string, string>; onAssignmentChange?: (id: string, value: string) => void; onAssign?: (id: string) => void; onUnassign?: (id: string) => void; onAssignmentResponse?: (id: string, accept: boolean, reason?: string) => void; onAction?: (item: OperationalAppointment, action: "detail" | "reschedule" | "cancel" | "audit") => void }) {
  return <div className="mt-5 overflow-x-auto rounded-2xl border bg-white"><table className="min-w-full text-left text-sm"><thead><tr>{["Customer", "Therapy / address", "Schedule", "Therapist", "Status", "Actions"].map((heading) => <th className="p-4" key={heading}>{heading}</th>)}</tr></thead><tbody>{items.map((item) => <tr className="border-t" key={item.id}><td className="p-4">{item.patient_name}<span className="block text-slate-500">{item.patient_identifier}</span>{item.originating_request&&<span className="block max-w-52 break-all text-xs">Request {item.originating_request}</span>}{physiotherapist&&<span className="block">{item.patient_mobile}</span>}</td><td className="p-4">{(item.requested_therapy_names?.length ? item.requested_therapy_names : [item.therapy_name]).join(", ")}<span className="block max-w-64 text-slate-600">{item.address_line_1}, {item.city} {item.pin_code}</span>{physiotherapist&&item.problem_description&&<span className="block max-w-64 text-slate-600">{item.problem_description}</span>}</td><td className="p-4">{new Date(item.scheduled_start).toLocaleString()}<span className="block text-xs">{item.duration_minutes} minutes</span></td><td className="p-4">{item.physiotherapist_name??"Unassigned"}<span className={`block text-xs ${item.assignment_status==="REJECTED"?"font-bold text-amber-700":""}`}>{item.assignment_status==="REJECTED"?"Reassignment required":item.assignment_status}</span>{!physiotherapist&&<span className="mt-2 flex flex-wrap gap-2"><select aria-label={`Assign ${item.patient_name}`} value={assignments?.[item.id]??""} onChange={event=>onAssignmentChange?.(item.id,event.target.value)} className="min-h-11 rounded-lg border px-2"><option value="">Select</option>{staffOptions?.map(([value,text])=><option key={value} value={value}>{text}</option>)}</select><button type="button" className="min-h-11 font-bold underline" onClick={()=>onAssign?.(item.id)}>Assign</button>{item.physiotherapist_name&&<button type="button" className="min-h-11 font-bold text-red-700 underline" onClick={()=>onUnassign?.(item.id)}>Cancel assignment</button>}</span>}</td><td className="p-4">{item.status}{item.assigned_manager_name&&<span className="block text-xs">Manager: {item.assigned_manager_name}</span>}</td><td className="p-4"><div className="flex flex-wrap gap-2">{physiotherapist&&item.assignment_status==="PENDING"&&<><button className="min-h-11 font-bold underline" onClick={()=>onAssignmentResponse?.(item.id,true)}>Accept assignment</button><button className="min-h-11 font-bold text-red-700 underline" onClick={()=>onAssignmentResponse?.(item.id,false,"Unable to cover this assignment")}>Decline assignment</button></>}{physiotherapist&&item.status==="CONFIRMED"&&<><button className="min-h-11 font-bold underline" onClick={()=>onStatus(item.id,"IN_PROGRESS")}>Start</button><button className="min-h-11 font-bold underline" onClick={()=>onStatus(item.id,"NO_SHOW")}>No show</button></>}{physiotherapist&&item.status==="IN_PROGRESS"&&<button className="min-h-11 font-bold underline" onClick={()=>onStatus(item.id,"COMPLETED")}>Complete</button>}{!physiotherapist&&<button className="min-h-11 font-bold underline" onClick={()=>onAction?.(item,"detail")}>View details</button>}{!physiotherapist&&item.status==="SCHEDULED"&&<button className="min-h-11 font-bold underline" onClick={()=>onStatus(item.id,"CONFIRMED")}>Confirm</button>}{!physiotherapist&&editableStatuses.includes(item.status)&&<><button className="min-h-11 font-bold underline" onClick={()=>onAction?.(item,"reschedule")}>Reschedule</button><button className="min-h-11 font-bold text-red-700 underline" onClick={()=>onAction?.(item,"cancel")}>Cancel</button></>}{!physiotherapist&&<button className="min-h-11 font-bold underline" onClick={()=>onAction?.(item,"audit")}>Audit</button>}</div></td></tr>)}</tbody></table>{items.length===0&&<p className="p-5 text-slate-600">No appointments found.</p>}</div>;
}

function LifecyclePanel({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) { return <aside aria-label={title} className="mt-5 rounded-2xl border border-emerald-200 bg-emerald-50 p-5"><div className="mb-4 flex justify-between"><h3 className="text-xl font-bold">{title}</h3><button onClick={onClose} className="font-bold underline">Close</button></div>{children}</aside>; }
function Detail({label,value}:{label:string;value:string}){return <div><dt className="font-bold">{label}</dt><dd className="break-words">{value}</dd></div>}
function OverrideFields() { return <><label className="flex min-h-11 items-center gap-2 font-semibold"><input name="override" type="checkbox"/>Owner policy override</label><Field name="override_reason" label="Structured override reason" required={false}/></>; }
function SubmitAction({ pending, label, error }: { pending: boolean; label: string; error?: string }) { return <><button disabled={pending} className="min-h-11 rounded-xl bg-emerald-700 px-4 font-bold text-white sm:col-span-2">{pending ? "Savingâ€¦" : label}</button>{error && <p role="alert" className="text-red-700 sm:col-span-2">{error}</p>}</>; }
function Field({ name, label, type = "text", required = true, value, defaultValue, onChange }: { name: string; label: string; type?: string; required?: boolean; value?: string; defaultValue?: string; onChange?: (value: string) => void }) { return <label className="grid gap-1 font-semibold">{label}<input name={name} type={type} required={required} value={value} defaultValue={defaultValue} onChange={onChange ? (event) => onChange(event.target.value) : undefined} min={type === "number" ? 30 : undefined} max={type === "number" ? 180 : undefined} className="min-h-11 rounded-xl border px-3"/></label>; }
function Select({ name, label, options, required = true, value, onChange }: { name: string; label: string; options?: string[][]; required?: boolean; value?: string; onChange?: (value: string) => void }) { return <label className="grid gap-1 font-semibold">{label}<select name={name} required={required} value={value} onChange={onChange ? (event) => onChange(event.target.value) : undefined} className="min-h-11 rounded-xl border px-3"><option value="">Select</option>{options?.map(([optionValue, text]) => <option key={optionValue} value={optionValue}>{text}</option>)}</select></label>; }
