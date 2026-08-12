"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { requestJson } from "@/lib/api/client";
import type { OperationalAppointmentPage } from "@/lib/appointments/contracts";

export function PaymentOperations() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["payment-operations"], queryFn: () => requestJson<OperationalAppointmentPage>("/api/schedule/operations?status=COMPLETED"), refetchInterval: 15_000 });
  const update = useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) => requestJson(`/api/schedule/${id}/payment`, { method: "POST", body: JSON.stringify(payload) }), onSuccess: () => client.invalidateQueries({ queryKey: ["payment-operations"] }) });
  return <section className="mt-8"><h2 className="text-2xl font-bold">Practitioner payments</h2><p className="text-slate-600">Operational records only; no payment gateway is connected.</p><div className="mt-4 grid gap-4 lg:grid-cols-2">{query.data?.results.map(item => <form key={item.id} onSubmit={event => { event.preventDefault(); const data = new FormData(event.currentTarget); update.mutate({ id: item.id, payload: { status: data.get("status"), payable_amount: data.get("amount") || null, reference: data.get("reference"), note: data.get("note") } }); }} className="grid gap-3 rounded-2xl border bg-white p-5 sm:grid-cols-2"><div className="sm:col-span-2"><strong>{item.physiotherapist_name}</strong><p>{item.therapy_name} · {new Date(item.scheduled_start).toLocaleDateString()}</p></div><label className="grid gap-1">Status<select name="status" defaultValue={item.payment_status ?? "PENDING"} className="min-h-12 rounded-xl border px-3">{["PENDING","PROCESSING","PAID","HELD"].map(value => <option key={value}>{value}</option>)}</select></label><label className="grid gap-1">Amount<input name="amount" type="number" min="0" step="0.01" className="min-h-12 rounded-xl border px-3"/></label><label className="grid gap-1">Reference<input name="reference" className="min-h-12 rounded-xl border px-3"/></label><label className="grid gap-1">Note<input name="note" className="min-h-12 rounded-xl border px-3"/></label><button disabled={update.isPending} className="min-h-12 rounded-xl bg-emerald-700 font-bold text-white sm:col-span-2">Save payment status</button></form>)}</div></section>;
}
