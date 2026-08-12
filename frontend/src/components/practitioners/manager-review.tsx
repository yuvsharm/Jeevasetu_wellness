"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { requestJson } from "@/lib/api/client";
import type { PractitionerApplication } from "@/lib/practitioners/contracts";

type ReviewInput = { id: string; action: "review" | "correction" | "approve" | "reject"; reason?: string };
const actionable: Record<string, ReviewInput["action"][]> = {
  SUBMITTED: ["review", "correction", "approve", "reject"],
  RESUBMITTED: ["review", "correction", "approve", "reject"],
  UNDER_REVIEW: ["correction", "approve", "reject"],
};

export function PractitionerReview() {
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [dialog, setDialog] = useState<{ id: string; action: "correction" | "reject" } | null>(null);
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState("");
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["practitioner-review", status, search],
    queryFn: () => requestJson<PractitionerApplication[]>(`/api/practitioners/applications?status=${status}&search=${encodeURIComponent(search)}`),
    refetchInterval: 15_000,
  });
  const review = useMutation({
    mutationFn: (input: ReviewInput) => requestJson<PractitionerApplication>(`/api/practitioners/applications/${input.id}/review`, { method: "POST", body: JSON.stringify({ action: input.action, reason: input.reason ?? "" }) }),
    onSuccess: async (value) => {
      setNotice(`${value.full_legal_name}: ${value.status.replaceAll("_", " ")}`);
      setDialog(null); setReason("");
      client.setQueriesData<PractitionerApplication[]>({ queryKey: ["practitioner-review"] }, (items) => items?.map((item) => item.id === value.id ? value : item));
      await client.invalidateQueries({ queryKey: ["practitioner-review"] });
    },
  });
  const verify = useMutation({ mutationFn: ({ kind, id }: { kind: "documents" | "competencies"; id: string }) => requestJson(`/api/practitioners/${kind}/${id}/verify`, { method: "POST", body: JSON.stringify({ verified: true }) }), onSuccess: () => client.invalidateQueries({ queryKey: ["practitioner-review"] }) });
  const act = (id: string, action: ReviewInput["action"]) => action === "correction" || action === "reject" ? setDialog({ id, action }) : review.mutate({ id, action });
  return <section className="mt-8" aria-labelledby="practitioner-review-heading">
    <h2 id="practitioner-review-heading" className="text-2xl font-bold">Practitioner applications</h2>
    <p className="mt-1 text-slate-600">Review qualifications, private evidence and competencies within your authorized clinic scope.</p>
    {notice && <p role="status" className="mt-4 rounded-xl bg-emerald-50 p-3 font-semibold text-emerald-900">{notice}</p>}
    {review.isError && <p role="alert" className="mt-4 rounded-xl bg-red-50 p-3 text-red-800">{review.error.message}</p>}
    <div className="mt-5 grid gap-3 sm:grid-cols-2"><input aria-label="Search applications" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search name, email or mobile" className="min-h-11 rounded-xl border px-3"/><select aria-label="Application status" value={status} onChange={e => setStatus(e.target.value)} className="min-h-11 rounded-xl border px-3"><option value="">Actionable applications</option>{["SUBMITTED","RESUBMITTED","UNDER_REVIEW","CORRECTION_REQUIRED","APPROVED","REJECTED"].map(item => <option key={item}>{item}</option>)}</select></div>
    <div className="mt-5 grid gap-4 xl:grid-cols-2">{query.data?.map(item => <article key={item.id} className="rounded-2xl border bg-white p-5"><div className="flex flex-wrap justify-between gap-3"><div><h3 className="text-xl font-bold">{item.full_legal_name}</h3><p className="text-sm text-slate-500">{item.category.replaceAll("_", " ")} · {item.highest_qualification}</p></div><span className="rounded-full bg-slate-100 px-3 py-2 text-xs font-bold">{item.status.replaceAll("_", " ")}</span></div>{item.reviewed_at && <p className="mt-3 text-sm text-slate-600">Reviewed by <strong>{item.reviewer_name || "Authorized reviewer"}</strong> · {new Date(item.reviewed_at).toLocaleString()}</p>}<dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2"><div><dt className="font-bold">Experience</dt><dd>{item.experience_years}y {item.experience_months}m</dd></div><div><dt className="font-bold">Location</dt><dd>{item.city}, {item.state}</dd></div></dl><div className="mt-4 grid gap-3 text-sm sm:grid-cols-2"><div><h4 className="font-bold">Private documents</h4>{item.documents.map(doc => <div key={doc.id} className="mt-2 flex flex-wrap items-center gap-2"><a href={`/api/practitioners/documents/${doc.id}`} className="break-all underline">{doc.original_name}</a><button disabled={verify.isPending} onClick={() => verify.mutate({ kind: "documents", id: doc.id })} className="min-h-11 font-bold text-emerald-800">Verify</button></div>)}</div><div><h4 className="font-bold">Competencies</h4>{item.competencies.map(skill => <div key={skill.id} className="mt-2 flex flex-wrap items-center gap-2"><span>{skill.therapy_name}</span><button disabled={verify.isPending} onClick={() => verify.mutate({ kind: "competencies", id: skill.id })} className="min-h-11 font-bold text-emerald-800">Verify</button></div>)}</div></div>{["SUBMITTED", "RESUBMITTED", "UNDER_REVIEW"].includes(item.status) && (!item.competencies.some(skill => skill.verification_status === "VERIFIED") || item.documents.filter(doc => doc.verification_status === "VERIFIED").length < 2) && <p role="note" className="mt-4 rounded-xl bg-amber-50 p-3 text-sm font-semibold text-amber-900">Approval requires at least one verified competency and two verified documents. Request correction if the applicant has not selected a service.</p>}<div className="mt-5 flex flex-wrap gap-2">{(actionable[item.status] ?? []).map(action => <button key={action} disabled={review.isPending} onClick={() => act(item.id, action)} className={`min-h-11 rounded-xl px-4 font-bold disabled:opacity-50 ${action === "approve" ? "bg-emerald-700 text-white" : action === "reject" ? "bg-red-100 text-red-800" : action === "correction" ? "bg-amber-100 text-amber-900" : "border"}`}>{review.isPending && review.variables?.id === item.id ? "Saving…" : action === "review" ? "Start Review" : action === "correction" ? "Request Correction" : action[0].toUpperCase() + action.slice(1)}</button>)}</div></article>)}{query.isPending && <p>Loading applications…</p>}</div>
    {dialog && <div role="dialog" aria-modal="true" aria-labelledby="review-reason-heading" className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4"><form onSubmit={event => { event.preventDefault(); review.mutate({ ...dialog, reason }); }} className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl"><h3 id="review-reason-heading" className="text-xl font-bold">{dialog.action === "correction" ? "Request correction" : "Reject application"}</h3><label className="mt-4 grid gap-2 font-semibold">Reason<textarea autoFocus required minLength={3} maxLength={500} value={reason} onChange={event => setReason(event.target.value)} rows={5} className="rounded-xl border p-3"/></label><div className="mt-4 flex flex-col gap-2 sm:flex-row"><button disabled={review.isPending || reason.trim().length < 3} className="min-h-12 rounded-xl bg-emerald-700 px-5 font-bold text-white">{review.isPending ? "Saving…" : "Confirm"}</button><button type="button" onClick={() => { setDialog(null); setReason(""); }} className="min-h-12 rounded-xl border px-5 font-bold">Cancel</button></div></form></div>}
  </section>;
}
