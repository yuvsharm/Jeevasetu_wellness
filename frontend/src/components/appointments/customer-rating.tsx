"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { requestJson } from "@/lib/api/client";
import type { CustomerReview, OperationalAppointment } from "@/lib/appointments/contracts";

type Draft = { stars: number; comment: string; preview: boolean };

export function CustomerRatingPanel({ appointmentId }: { appointmentId?: string }) {
  const client = useQueryClient();
  const sectionRef = useRef<HTMLElement>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const query = useQuery({
    queryKey: ["customer-operational"],
    queryFn: () => requestJson<OperationalAppointment[]>("/api/schedule/my-appointments"),
  });
  const rate = useMutation({
    mutationFn: (value: { id: string; stars: number; comment: string }) =>
      requestJson<CustomerReview>(`/api/schedule/my-appointments/${value.id}/rating`, {
        method: "POST",
        body: JSON.stringify({ stars: value.stars, comment: value.comment }),
      }),
    onSuccess: (rating, value) => {
      client.setQueryData<OperationalAppointment[]>(["customer-operational"], (current) =>
        current?.map((item) => item.id === value.id ? { ...item, rating } : item),
      );
      void client.invalidateQueries({ queryKey: ["customer-operational"] });
    },
  });
  const completed = query.data?.filter((item) =>
    item.status === "COMPLETED"
    && item.assignment_status === "ACCEPTED"
    && Boolean(item.physiotherapist_name)
    && (!appointmentId || item.id === appointmentId)
  ) ?? [];

  useEffect(() => {
    if (!appointmentId || query.isPending || completed.length === 0) return;
    let frame = 0;
    const focusRating = () => {
      if (window.location.hash !== "#rating") return;
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        sectionRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
        sectionRef.current?.focus({ preventScroll: true });
      });
    };
    focusRating();
    window.addEventListener("hashchange", focusRating);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("hashchange", focusRating);
    };
  }, [appointmentId, completed.length, query.isPending]);

  if (!query.isPending && completed.length === 0) return null;
  return <section id={appointmentId ? "rating" : undefined} ref={sectionRef} tabIndex={appointmentId ? -1 : undefined} aria-labelledby="customer-rating-title" className="scroll-mt-24 outline-none">
    <h2 id="customer-rating-title" className="text-2xl font-bold">Rate your therapist</h2>
    <p className="mt-1 text-slate-600">Choose 1–5 stars. A written review is optional and feedback can be submitted only once.</p>
    <div className="mt-4 grid gap-4 lg:grid-cols-2">{completed.map((item) => {
      if (item.rating) return <article key={item.id} className="min-w-0 rounded-2xl border bg-white p-5"><strong>Feedback submitted</strong><p className="mt-1 break-words text-sm text-slate-600">{item.therapy_name}{item.physiotherapist_name ? ` · ${item.physiotherapist_name}` : ""}</p><p className="mt-2 text-amber-600" aria-label={`${item.rating.stars} out of 5 stars`}>{"★".repeat(item.rating.stars)}{"☆".repeat(5 - item.rating.stars)}</p>{item.rating.comment && <p className="mt-2 whitespace-pre-wrap break-words text-slate-700">{item.rating.comment}</p>}<p className="mt-3 text-sm font-semibold">Status: {item.rating.status_display}</p>{item.rating.moderation_status === "HIDDEN" && <p className="mt-1 break-words text-sm text-slate-600">Reason: {item.rating.moderation_reason}</p>}</article>;
      const draft = drafts[item.id] ?? { stars: 0, comment: "", preview: false };
      return <form key={item.id} onSubmit={(event) => {
        event.preventDefault();
        if (!draft.preview) {
          setDrafts({ ...drafts, [item.id]: { ...draft, preview: true } });
          return;
        }
        rate.mutate({ id: item.id, stars: draft.stars, comment: draft.comment });
      }} className="grid min-w-0 gap-3 rounded-2xl border bg-white p-4 sm:p-5">
        <div className="min-w-0"><strong className="break-words">{item.therapy_name} · {new Date(item.scheduled_start).toLocaleDateString()}</strong><p className="mt-1 break-words text-sm text-slate-600">Therapist: {item.physiotherapist_name}</p></div>
        <fieldset><legend className="font-semibold">Rating</legend><div className="mt-1 flex flex-wrap gap-1">{[1, 2, 3, 4, 5].map((stars) => <label key={stars} className="cursor-pointer"><input className="sr-only" type="radio" name={`stars-${item.id}`} value={stars} checked={draft.stars === stars} onChange={() => setDrafts({ ...drafts, [item.id]: { ...draft, stars, preview: false } })}/><span className={`text-3xl ${stars <= draft.stars ? "text-amber-500" : "text-slate-300"}`} aria-hidden="true">★</span><span className="sr-only">{stars} stars</span></label>)}</div></fieldset>
        <label className="grid min-w-0 gap-1 font-semibold">Review (optional)<textarea maxLength={1000} value={draft.comment} onChange={(event) => setDrafts({ ...drafts, [item.id]: { ...draft, comment: event.target.value, preview: false } })} className="min-w-0 rounded-xl border p-3"/></label>
        {draft.preview && <div className="min-w-0 rounded-xl bg-emerald-50 p-3"><strong>Review before submitting</strong><p className="break-words">{draft.stars} stars{draft.comment.trim() ? ` · ${draft.comment}` : " · No written review"}</p><p className="mt-1 text-xs">You cannot edit or delete this review after submission.</p></div>}
        <button disabled={rate.isPending || draft.stars < 1} className="min-h-12 rounded-xl bg-emerald-700 px-4 font-bold text-white">{rate.isPending ? "Submitting…" : draft.preview ? "Submit review" : "Review submission"}</button>
        {rate.isError && <p role="alert" className="break-words text-red-700">{rate.error.message}</p>}
      </form>;
    })}</div>
  </section>;
}
