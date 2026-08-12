"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { requestJson } from "@/lib/api/client";
import type { OperationalAppointment } from "@/lib/appointments/contracts";

export function CustomerRatingPanel() {
  const client = useQueryClient();
  const [submitted, setSubmitted] = useState<string[]>([]);
  const query = useQuery({ queryKey: ["customer-appointments"], queryFn: () => requestJson<OperationalAppointment[]>("/api/schedule/my-appointments") });
  const rate = useMutation({ mutationFn: ({ id, stars, comment }: { id: string; stars: number; comment: string }) => requestJson(`/api/schedule/my-appointments/${id}/rating`, { method: "POST", body: JSON.stringify({ stars, comment }) }), onSuccess: (_, value) => { setSubmitted(current => [...current, value.id]); client.invalidateQueries({ queryKey: ["customer-appointments"] }); } });
  const completed = query.data?.filter(item => item.status === "COMPLETED" && !submitted.includes(item.id)) ?? [];
  return <section className="mt-8"><h2 className="text-2xl font-bold">Rate completed services</h2><div className="mt-4 grid gap-4 sm:grid-cols-2">{completed.map(item => <form key={item.id} onSubmit={event => { event.preventDefault(); const data = new FormData(event.currentTarget); rate.mutate({ id: item.id, stars: Number(data.get("stars")), comment: String(data.get("comment") ?? "") }); }} className="grid gap-3 rounded-2xl border bg-white p-5"><strong>{item.therapy_name}</strong><p>{new Date(item.scheduled_start).toLocaleDateString()}</p><label className="grid gap-1 font-semibold">Rating<select name="stars" required className="min-h-12 rounded-xl border px-3"><option value="">Select</option>{[5,4,3,2,1].map(stars => <option key={stars} value={stars}>{stars} stars</option>)}</select></label><label className="grid gap-1 font-semibold">Optional review<textarea name="comment" maxLength={1000} className="rounded-xl border p-3"/></label><button disabled={rate.isPending} className="min-h-12 rounded-xl bg-emerald-700 px-4 font-bold text-white">Submit rating</button>{rate.isError && <p role="alert" className="text-red-700">{rate.error.message}</p>}</form>)}</div></section>;
}
