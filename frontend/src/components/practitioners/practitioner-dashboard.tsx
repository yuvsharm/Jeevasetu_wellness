"use client";

import { useQuery } from "@tanstack/react-query";
import Image from "next/image";
import { requestJson } from "@/lib/api/client";
import type { OperationalAppointment, PractitionerPayment } from "@/lib/appointments/contracts";
import type { PractitionerApplication } from "@/lib/practitioners/contracts";

export function PractitionerDashboardOverview() {
  const applications = useQuery({ queryKey: ["practitioner-dashboard-application"], queryFn: () => requestJson<PractitionerApplication[]>("/api/practitioners/me") });
  const appointments = useQuery({ queryKey: ["assigned-appointments"], queryFn: () => requestJson<OperationalAppointment[]>("/api/schedule/assigned-to-me"), refetchInterval: 15_000 });
  const payments = useQuery({ queryKey: ["practitioner-payments"], queryFn: () => requestJson<PractitionerPayment[]>("/api/schedule/assigned-to-me/payments") });
  const application = applications.data?.find(item => item.status === "APPROVED");
  const items = appointments.data ?? []; const now = new Date(); const today = now.toDateString();
  const offers = items.filter(item => item.assignment_status === "PENDING");
  const todayItems = items.filter(item => new Date(item.scheduled_start).toDateString() === today && item.status !== "CANCELLED");
  const completed = items.filter(item => item.status === "COMPLETED"); const cancelled = items.filter(item => item.status === "CANCELLED");
  const upcoming = items.filter(item => new Date(item.scheduled_start) > now && !["COMPLETED", "CANCELLED"].includes(item.status));
  const ratings = completed.filter(item => item.rating_stars); const average = ratings.length ? ratings.reduce((sum, item) => sum + (item.rating_stars ?? 0), 0) / ratings.length : null;
  if (!application) return null;
  return <div className="mt-6 grid min-w-0 gap-6">
    <section className="grid gap-5 rounded-2xl border bg-white p-5 md:grid-cols-[8rem_1fr]"><Image src={`/api/practitioners/me/${application.id}/profile-photo`} alt={`${application.full_legal_name} profile`} width={128} height={128} unoptimized className="size-32 rounded-2xl object-cover"/><div><p className="text-sm font-bold uppercase tracking-wide text-emerald-700">Approved · JeevaSetu Verified</p><h2 className="mt-1 text-2xl font-bold">{application.full_legal_name}</h2><p>{application.highest_qualification}{application.specialization ? ` · ${application.specialization}` : ""}</p><p className="text-slate-600">{application.category.replaceAll("_", " ")} · {application.experience_years}y {application.experience_months}m experience</p><div className="mt-3 flex flex-wrap gap-2">{application.competencies.filter(item => item.verification_status === "VERIFIED").map(item => <span key={item.id} className="rounded-full bg-emerald-50 px-3 py-1 text-sm font-semibold">{item.therapy_name}</span>)}</div></div></section>
    <section><h2 className="text-2xl font-bold">Today & work summary</h2><div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">{[["Pending offers",offers.length],["Today",todayItems.length],["Upcoming",upcoming.length],["Completed",completed.length],["Cancelled",cancelled.length],["Average rating",average ? average.toFixed(1) : "Not rated"]].map(([label,value]) => <article key={label} className="rounded-2xl border bg-white p-4"><p className="text-sm text-slate-600">{label}</p><strong className="text-2xl">{value}</strong></article>)}</div></section>
    <section><h2 className="text-2xl font-bold">Ratings and reviews</h2><div className="mt-3 grid gap-3 sm:grid-cols-2">{ratings.slice(0,6).map(item => <article key={item.id} className="rounded-2xl border bg-white p-4"><strong>{item.rating_stars}/5 stars</strong>{item.rating_comment && <p className="mt-2 text-slate-700">{item.rating_comment}</p>}</article>)}{ratings.length === 0 && <p className="text-slate-600">No customer ratings yet.</p>}</div></section>
    <section><h2 className="text-2xl font-bold">Payments and earnings</h2><div className="mt-3 grid gap-3">{payments.data?.map(item => <article key={item.id} className="rounded-2xl border bg-white p-4 sm:flex sm:items-center sm:justify-between"><div><strong>{item.therapy_name}</strong><p className="text-sm text-slate-600">{new Date(item.service_date).toLocaleDateString()}</p></div><div className="mt-2 sm:mt-0 sm:text-right"><strong>{item.status}</strong><p>{item.payable_amount ? `₹${item.payable_amount}` : "Amount not configured"}</p>{item.reference && <p className="text-sm">Ref: {item.reference}</p>}</div></article>)}{payments.data?.length === 0 && <p className="text-slate-600">No payment records yet.</p>}</div></section>
  </div>;
}
