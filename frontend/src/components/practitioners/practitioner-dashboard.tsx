"use client";

import { useQuery } from "@tanstack/react-query";
import { requestJson } from "@/lib/api/client";
import type { OperationalAppointment } from "@/lib/appointments/contracts";
import type { PractitionerApplication } from "@/lib/practitioners/contracts";

function label(value: string) { return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, letter => letter.toUpperCase()); }
function visitState(item: OperationalAppointment) {
  if (item.status === "COMPLETED") return "Completed";
  if (item.status === "IN_PROGRESS") return "Service in progress";
  if (item.journey_status === "ARRIVED") return "Arrived";
  if (item.journey_status === "EN_ROUTE") return "En route";
  if (item.assignment_status === "REJECTED") return "Declined";
  if (item.assignment_status === "PENDING") return "Awaiting response";
  return item.assignment_status === "ACCEPTED" ? "Accepted" : label(item.status);
}

export function PractitionerDashboardOverview() {
  const applications = useQuery({ queryKey: ["practitioner-dashboard-application"], queryFn: () => requestJson<PractitionerApplication[]>("/api/practitioners/me"), refetchInterval: 30_000 });
  const appointments = useQuery({ queryKey: ["assigned-appointments"], queryFn: () => requestJson<OperationalAppointment[]>("/api/schedule/assigned-to-me"), refetchInterval: 15_000 });
  const application = applications.data?.[0];
  const items = appointments.data ?? []; const now = new Date(); const today = now.toDateString();
  const active = items.filter(item => !["CANCELLED", "COMPLETED"].includes(item.status));
  const schedule = active.filter(item => new Date(item.scheduled_end) >= now || new Date(item.scheduled_start).toDateString() === today).sort((a, b) => new Date(a.scheduled_start).getTime() - new Date(b.scheduled_start).getTime());
  const counters = [
    ["Today", items.filter(item => new Date(item.scheduled_start).toDateString() === today && item.status !== "CANCELLED").length],
    ["New assignments", items.filter(item => item.assignment_status === "PENDING").length],
    ["Accepted / upcoming", active.filter(item => item.assignment_status === "ACCEPTED" && item.journey_status === "NOT_STARTED").length],
    ["En route", active.filter(item => item.journey_status === "EN_ROUTE").length],
    ["Arrived", active.filter(item => item.journey_status === "ARRIVED" && item.status !== "IN_PROGRESS").length],
    ["In service", items.filter(item => item.status === "IN_PROGRESS").length],
    ["Completed", items.filter(item => item.status === "COMPLETED").length],
    ["Declined", items.filter(item => item.assignment_status === "REJECTED").length],
  ] as const;
  return <div className="mt-6 grid min-w-0 gap-7">
    {application && <section className="rounded-2xl border bg-white p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm font-bold uppercase tracking-wide text-emerald-700">Application status</p><h2 className="mt-1 text-2xl font-bold">{label(application.status)}</h2></div><span className="rounded-full bg-emerald-50 px-3 py-2 text-sm font-bold text-emerald-900">{application.status === "APPROVED" ? "Operational access approved" : "Access pending review"}</span></div>{(application.correction_reason || application.rejection_reason) && <p className="mt-4 rounded-xl bg-amber-50 p-4 text-amber-950"><strong>Manager reason:</strong> {application.correction_reason || application.rejection_reason}</p>}</section>}
    <section aria-labelledby="therapist-summary-heading"><h2 id="therapist-summary-heading" className="text-2xl font-bold">Today at a glance</h2><div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8">{counters.map(([name, value]) => <article key={name} className="min-w-0 rounded-2xl border bg-white p-4"><p className="text-sm text-slate-600">{name}</p><strong className="mt-1 block text-2xl">{value}</strong></article>)}</div></section>
    <section aria-labelledby="daily-schedule-heading"><div className="flex flex-wrap items-end justify-between gap-2"><div><h2 id="daily-schedule-heading" className="text-2xl font-bold">Daily schedule</h2><p className="text-slate-600">Today and upcoming visits in chronological order.</p></div><span className="rounded-full bg-slate-100 px-3 py-2 text-sm font-semibold">{schedule.length} visit{schedule.length === 1 ? "" : "s"}</span></div><div className="mt-4 grid gap-3">{schedule.map(item => <article key={item.id} className="min-w-0 rounded-2xl border bg-white p-4 sm:flex sm:items-center sm:justify-between sm:gap-5"><div className="min-w-0"><p className="font-bold">{new Date(item.scheduled_start).toLocaleString([], { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })}</p><p className="break-words text-slate-700">{(item.requested_therapy_names?.length ? item.requested_therapy_names : [item.therapy_name]).join(", ")}</p><p className="text-sm text-slate-600">{item.duration_minutes} min · {item.city || "Service area pending"}{item.region ? `, ${item.region}` : ""}</p></div><span className="mt-3 inline-flex min-h-11 items-center rounded-full bg-emerald-50 px-3 py-2 text-sm font-bold text-emerald-900 sm:mt-0">{visitState(item)}</span></article>)}{appointments.isPending && <p>Loading schedule…</p>}{!appointments.isPending && schedule.length === 0 && <p className="rounded-2xl border bg-white p-5 text-slate-600">No visits scheduled for today or later.</p>}</div></section>
  </div>;
}
