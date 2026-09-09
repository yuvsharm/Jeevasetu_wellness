"use client";

import Image from "next/image";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { requestJson } from "@/lib/api/client";
import type { PractitionerApplication } from "@/lib/practitioners/contracts";
import { formatDob } from "./dob-field";

type ReviewInput = { id: string; action: "review" | "correction" | "approve" | "reject"; reason?: string };
type VerifyInput = { id: string; verified: boolean };
const actions: Record<string, ReviewInput["action"][]> = {
  SUBMITTED: ["review"], RESUBMITTED: ["review"], UNDER_REVIEW: ["correction", "approve", "reject"],
};
const qualifications: Record<string, string> = {
  BPT: "BPT", MPT: "MPT", DPT: "DPT", OTHER_PHYSIOTHERAPY: "Other physiotherapy qualification",
  WELLNESS_CERTIFICATION: "Wellness qualification/certification",
};
const dayNames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const labelStatus = (value: string) => value.replaceAll("_", " ").toLowerCase().replace(/^./, char => char.toUpperCase());
const experience = (item: PractitionerApplication) => `${item.experience_years}y ${item.experience_months}m`;
const qualification = (item: PractitionerApplication) => item.qualification_title || qualifications[item.highest_qualification] || labelStatus(item.highest_qualification);

function Initial({ item }: { item: PractitionerApplication }) {
  return item.has_profile_photo
    ? <Image src={`/api/practitioners/applications/${item.id}/profile-photo`} alt={`${item.full_legal_name} profile`} width={44} height={44} unoptimized className="h-11 w-11 rounded-full object-cover" />
    : <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-emerald-100 font-bold text-emerald-800">{item.full_legal_name.trim().charAt(0).toUpperCase() || "P"}</span>;
}

function Detail({ label, value }: { label: string; value?: string | number | null }) {
  if (value === undefined || value === null || value === "") return null;
  return <div><dt className="text-xs font-bold uppercase tracking-wide text-slate-500">{label}</dt><dd className="mt-1 break-words">{value}</dd></div>;
}

export function PractitionerReview() {
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [dialog, setDialog] = useState<{ id: string; action: "correction" | "reject" } | null>(null);
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState("");
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["practitioner-review", status, search],
    queryFn: () => requestJson<PractitionerApplication[]>(`/api/practitioners/applications?status=${status}&search=${encodeURIComponent(search)}`),
    refetchInterval: 15_000,
  });
  const refresh = async () => Promise.all([
    client.invalidateQueries({ queryKey: ["practitioner-review"] }),
    client.invalidateQueries({ queryKey: ["staff"] }),
    client.invalidateQueries({ queryKey: ["request-eligible"] }),
  ]);
  const review = useMutation({
    mutationFn: (input: ReviewInput) => requestJson<PractitionerApplication>(`/api/practitioners/applications/${input.id}/review`, { method: "POST", body: JSON.stringify({ action: input.action, reason: input.reason ?? "" }) }),
    onSuccess: async value => {
      const outcome = value.correction_reason || value.rejection_reason;
      const reviewed = value.reviewed_at ? ` by ${value.reviewer_name || "authorized reviewer"} at ${new Date(value.reviewed_at).toLocaleString()}` : "";
      setNotice(`${value.full_legal_name}: ${labelStatus(value.status)}${reviewed}${outcome ? `. Reason: ${outcome}` : ""}`);
      setDialog(null); setReason("");
      client.setQueriesData<PractitionerApplication[]>({ queryKey: ["practitioner-review"] }, items => items?.map(item => item.id === value.id ? value : item));
      await refresh();
    },
  });
  const verify = useMutation({
    mutationFn: ({ id, verified }: VerifyInput) => requestJson<{ verification_status: string }>(`/api/practitioners/documents/${id}/verify`, { method: "POST", body: JSON.stringify({ verified }) }),
    onSuccess: async result => { setNotice(`Document ${result.verification_status.toLowerCase()}.`); await refresh(); },
  });
  const remove = useMutation({
    mutationFn: (id: string) => requestJson(`/api/practitioners/competencies/${id}`, { method: "DELETE" }),
    onSuccess: async () => { setNotice("Therapy removed from the application."); await refresh(); },
  });
  const act = (id: string, action: ReviewInput["action"]) => action === "correction" || action === "reject" ? setDialog({ id, action }) : review.mutate({ id, action });
  const removeCompetency = (competency: PractitionerApplication["competencies"][number]) => {
    if (!window.confirm(`Remove ${competency.therapy_name} from this practitioner's therapies?`)) return;
    remove.mutate(competency.id);
  };

  return <section className="mt-8" aria-labelledby="practitioner-review-heading">
    <h2 id="practitioner-review-heading" className="text-2xl font-bold">Practitioner applications</h2>
    <p className="mt-1 text-slate-600">Expand one application to review its evidence, competencies and actions.</p>
    {notice && <p role="status" className="mt-4 rounded-xl bg-emerald-50 p-3 font-semibold text-emerald-900">{notice}</p>}
    {(review.isError || verify.isError || remove.isError) && <p role="alert" className="mt-4 rounded-xl bg-red-50 p-3 text-red-800">{(review.error || verify.error || remove.error)?.message}</p>}
    <div className="mt-5 grid gap-3 sm:grid-cols-2"><input aria-label="Search applications" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search name, email or mobile" className="min-h-11 rounded-xl border px-3"/><select aria-label="Application status" value={status} onChange={event => setStatus(event.target.value)} className="min-h-11 rounded-xl border px-3"><option value="">Actionable applications</option>{["SUBMITTED","RESUBMITTED","UNDER_REVIEW","CORRECTION_REQUIRED","APPROVED","REJECTED"].map(item => <option key={item} value={item}>{labelStatus(item)}</option>)}</select></div>
    <div className="mt-5 space-y-3">{query.data?.map(item => {
      const open = expanded === item.id;
      const location = [item.city, item.state].filter(Boolean).join(", ");
      return <article key={item.id} className="overflow-hidden rounded-2xl border bg-white shadow-sm">
        <button type="button" aria-expanded={open} onClick={() => setExpanded(open ? null : item.id)} className="grid w-full items-center gap-3 p-4 text-left sm:grid-cols-[auto_1.5fr_1fr_1fr_auto_auto_auto_auto]">
          <Initial item={item}/><span className="font-bold">{item.full_legal_name}</span><span className="text-sm">{item.category === "WELLNESS" ? "Naturopathy Practitioner" : "Physiotherapist"}</span><span className="text-sm">{qualification(item)}</span><span className="text-sm">{experience(item)}</span><span className="text-sm">{item.submitted_at ? new Date(item.submitted_at).toLocaleDateString("en-IN") : "Not submitted"}</span><span className="rounded-full bg-slate-100 px-3 py-2 text-xs font-bold">{labelStatus(item.status)}</span><span aria-hidden="true" className="text-xl">{open ? "▲" : "▼"}</span>
        </button>
        {open && <div className="border-t bg-slate-50/50 p-4 sm:p-6">
          <div className="grid gap-4 lg:grid-cols-2">
            <section className="rounded-xl bg-white p-4"><h3 className="font-bold">1. Personal / Professional</h3><dl className="mt-3 grid gap-3 sm:grid-cols-2"><Detail label="Date of birth" value={formatDob(item.date_of_birth)}/><Detail label="Age" value={item.age == null ? undefined : `${item.age} years`}/><Detail label="Gender" value={labelStatus(item.gender)}/><Detail label="Email" value={item.email}/><Detail label="Mobile" value={item.mobile_number}/><Detail label="Address" value={item.current_address}/><Detail label="Location" value={location}/></dl></section>
            <section className="rounded-xl bg-white p-4"><h3 className="font-bold">2. Qualification</h3><dl className="mt-3 grid gap-3 sm:grid-cols-2"><Detail label="Qualification" value={qualification(item)}/><Detail label="Specialization" value={item.specialization}/><Detail label="College / institute" value={item.college_institute}/><Detail label="Awarding body" value={item.awarding_body}/><Detail label="Passing year" value={item.passing_year}/><Detail label="Registration" value={item.registration_number}/></dl></section>
            <section className="rounded-xl bg-white p-4"><h3 className="font-bold">3. Experience</h3><dl className="mt-3 grid gap-3 sm:grid-cols-2"><Detail label="Total" value={experience(item)}/><Detail label="Recent organization" value={item.recent_organization}/><Detail label="Home-service experience" value={item.has_home_service_experience ? "Yes" : "No"}/><Detail label="Previous experience" value={item.previous_experience}/></dl></section>
            <section className="rounded-xl bg-white p-4"><h3 className="font-bold">4. Service Areas</h3><p className="mt-3">{item.service_area_names?.filter(Boolean).join(", ") || location || "No service area selected"}</p></section>
            <section className="rounded-xl bg-white p-4"><h3 className="font-bold">5. Working Schedule</h3><p className="mt-3">{item.working_days?.length ? item.working_days.map(day => dayNames[day]).join(", ") : "No working days selected"}</p>{item.working_hours_start && item.working_hours_end && <p className="mt-1">{item.working_hours_start.slice(0,5)}–{item.working_hours_end.slice(0,5)}</p>}{item.availability_notes && <p className="mt-1 text-sm text-slate-600">{item.availability_notes}</p>}</section>
            <section className="rounded-xl bg-white p-4"><h3 className="font-bold">6. Professional Bio</h3><p className="mt-3 whitespace-pre-wrap">{item.bio || "No professional bio submitted."}</p></section>
            <section className="rounded-xl bg-white p-4"><h3 className="font-bold">7. Therapy Competencies</h3><div className="mt-3 max-h-72 space-y-2 overflow-auto">{item.competencies.filter(skill => skill.verification_status !== "REJECTED").map(skill => <div key={skill.id} className="flex items-center justify-between gap-3 rounded-lg border p-3"><span className="font-semibold">{skill.therapy_name}</span><button aria-label={`Remove ${skill.therapy_name}`} disabled={remove.isPending} onClick={() => removeCompetency(skill)} className="min-h-11 px-2 text-xl text-red-700">×</button></div>)}{item.competencies.every(skill => skill.verification_status === "REJECTED") && <p>No therapies claimed.</p>}</div></section>
            <section className="rounded-xl bg-white p-4"><h3 className="font-bold">8. Documents</h3><div className="mt-3 space-y-2">{item.documents.map(document => <div key={document.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3"><a href={`/api/practitioners/documents/${document.id}`} target="_blank" rel="noreferrer" className="break-all underline">{document.original_name}</a><span className="flex items-center gap-2"><span>{labelStatus(document.verification_status)}</span>{document.verification_status !== "VERIFIED" && <button disabled={verify.isPending} onClick={() => verify.mutate({ id: document.id, verified: true })} className="button-secondary">Verify</button>}</span></div>)}</div></section>
          </div>
          {(item.correction_reason || item.rejection_reason) && <p className="mt-4 rounded-xl bg-white p-3 text-sm"><strong>Outcome reason:</strong> {item.correction_reason || item.rejection_reason}</p>}
          {item.status === "UNDER_REVIEW" && (!item.competencies.some(skill => skill.verification_status !== "REJECTED") || !item.documents.some(document => document.kind === "GOVERNMENT_ID" && document.verification_status === "VERIFIED") || !item.documents.some(document => document.kind === "QUALIFICATION" && document.verification_status === "VERIFIED")) && <p role="note" className="mt-4 rounded-xl bg-amber-50 p-3 text-sm font-semibold text-amber-900">Approval requires at least one selected therapy, a verified Government ID, and a verified qualification document.</p>}
          <section className="mt-4 rounded-xl bg-white p-4"><h3 className="font-bold">9. Review Actions</h3><div className="mt-3 flex flex-wrap gap-2">{(actions[item.status] ?? []).map(action => <button key={action} disabled={review.isPending} onClick={() => act(item.id, action)} className={`min-h-11 rounded-xl px-4 font-bold disabled:opacity-50 ${action === "approve" ? "bg-emerald-700 text-white" : action === "reject" ? "bg-red-100 text-red-800" : action === "correction" ? "bg-amber-100 text-amber-900" : "border"}`}>{review.isPending && review.variables?.id === item.id ? "Saving…" : action === "review" ? "Start Review" : action === "correction" ? "Request Correction" : labelStatus(action)}</button>)}</div></section>
          <button type="button" onClick={() => setExpanded(null)} className="mt-4 min-h-11 w-full rounded-xl border font-bold">Collapse / Roll Up ▲</button>
        </div>}
      </article>;
    })}{query.isPending && <p>Loading applications…</p>}</div>
    {dialog && <div role="dialog" aria-modal="true" aria-labelledby="review-reason-heading" className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4"><form onSubmit={event => { event.preventDefault(); review.mutate({ ...dialog, reason }); }} className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl"><h3 id="review-reason-heading" className="text-xl font-bold">{dialog.action === "correction" ? "Request correction" : "Reject application"}</h3><label className="mt-4 grid gap-2 font-semibold">Reason<textarea autoFocus required minLength={3} maxLength={500} value={reason} onChange={event => setReason(event.target.value)} rows={5} className="rounded-xl border p-3"/></label><div className="mt-4 flex flex-col gap-2 sm:flex-row"><button disabled={review.isPending || reason.trim().length < 3} className="min-h-12 rounded-xl bg-emerald-700 px-5 font-bold text-white">{review.isPending ? "Saving…" : "Confirm"}</button><button type="button" onClick={() => { setDialog(null); setReason(""); }} className="min-h-12 rounded-xl border px-5 font-bold">Cancel</button></div></form></div>}
  </section>;
}
