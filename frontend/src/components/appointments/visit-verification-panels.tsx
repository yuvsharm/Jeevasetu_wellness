"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { requestJson } from "@/lib/api/client";
import type {
  OperationalAppointment,
  OperationalAppointmentPage,
  VisitVerificationStatus,
} from "@/lib/appointments/contracts";

function StatusBadge({ value }: { value: VisitVerificationStatus }) {
  return (
    <span className="inline-flex min-h-11 items-center rounded-full bg-emerald-50 px-3 py-2 text-sm font-bold text-emerald-900">
      {value.status.replaceAll("_", " ")}
    </span>
  );
}

export function OperationsVisitVerificationPanel() {
  const query = useQuery({
    queryKey: ["visit-verification-operations"],
    queryFn: () => requestJson<OperationalAppointmentPage>("/api/schedule/operations"),
  });
  return (
    <section className="mt-8" aria-labelledby="operations-visit-verification-heading">
      <h2 id="operations-visit-verification-heading" className="text-2xl font-bold">
        Visit verification status
      </h2>
      <p className="text-slate-600">Arrival status only. OTP values are never available here.</p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {query.data?.results.map((item) => (
          <article key={item.id} className="min-w-0 rounded-2xl border bg-white p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <h3 className="truncate font-bold">{item.patient_name}</h3>
                <p className="text-sm text-slate-600">{item.therapy_name}</p>
              </div>
              <StatusBadge value={item.visit_verification} />
            </div>
            <p className="mt-2 text-sm">{new Date(item.scheduled_start).toLocaleString()}</p>
            <p className="text-sm">Physiotherapist: {item.physiotherapist_name ?? "Unassigned"}</p>
            {item.visit_verification.verified_at && (
              <p className="mt-2 text-sm font-semibold">
                Verified {new Date(item.visit_verification.verified_at).toLocaleString()}
              </p>
            )}
            {item.visit_verification.failed_attempt_warning && (
              <p className="mt-2 text-sm font-semibold text-amber-800">Failed-attempt warning</p>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

export function PhysiotherapistVisitVerificationPanel() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["visit-verification-physiotherapist"],
    queryFn: () => requestJson<OperationalAppointment[]>("/api/schedule/assigned-to-me"),
  });
  const verify = useMutation({
    mutationFn: ({ id, otp }: { id: string; otp: string }) =>
      requestJson(`/api/schedule/assigned-to-me/${id}/visit-verification`, {
        method: "POST",
        body: JSON.stringify({ otp }),
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["visit-verification-physiotherapist"] });
      client.invalidateQueries({ queryKey: ["assigned-appointments"] });
    },
  });
  function submit(event: React.FormEvent<HTMLFormElement>, id: string) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    verify.mutate({ id, otp: String(data.get("otp")) });
  }
  const eligible =
    query.data?.filter(
      (item) => item.status === "CONFIRMED" && item.assignment_status === "ACCEPTED",
    ) ?? [];
  return (
    <section className="mt-8" aria-labelledby="physio-visit-verification-heading">
      <h2 id="physio-visit-verification-heading" className="text-2xl font-bold">
        Verify Customer Arrival
      </h2>
      <p className="text-slate-600">Enter the OTP shared by the Customer after you arrive.</p>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        {eligible.map((item) => (
          <article key={item.id} className="min-w-0 rounded-2xl border bg-white p-5">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h3 className="font-bold">{item.patient_name}</h3>
                <p className="text-sm text-slate-600">{item.therapy_name}</p>
              </div>
              <StatusBadge value={item.visit_verification} />
            </div>
            {item.visit_verification.status === "VERIFIED" ? (
              <p className="mt-4 font-semibold text-emerald-800">
                ✓ Customer verified<br />✓ Check-in verified<br />
                {item.visit_verification.verified_at &&
                  `✓ ${new Date(item.visit_verification.verified_at).toLocaleString()}`}
              </p>
            ) : (
              <form
                className="mt-4 grid gap-3"
                aria-label={`Verify arrival for ${item.patient_name}`}
                onSubmit={(event) => submit(event, item.id)}
              >
                <label className="grid gap-1 font-semibold">
                  6-digit Visit OTP
                  <input
                    name="otp"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="\d{6}"
                    maxLength={6}
                    required
                    className="min-h-11 rounded-xl border px-3 text-lg tracking-widest"
                  />
                </label>
                <button
                  disabled={verify.isPending}
                  className="min-h-11 rounded-xl bg-emerald-700 px-4 font-bold text-white"
                >
                  {verify.isPending ? "Verifying…" : "Verify Visit"}
                </button>
                {verify.isError && <p role="alert" className="text-red-700">{verify.error.message}</p>}
              </form>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

export function CustomerVisitVerificationPanel() {
  const client = useQueryClient();
  const [delivered, setDelivered] = useState<
    Record<string, { otp: string; expires_at: string | null }>
  >({});
  const query = useQuery({
    queryKey: ["visit-verification-customer"],
    queryFn: () => requestJson<OperationalAppointment[]>("/api/schedule/my-appointments"),
  });
  const issue = useMutation({
    mutationFn: (id: string) =>
      requestJson<{ otp: string; expires_at: string | null }>(
        `/api/schedule/my-appointments/${id}/visit-verification`,
        { method: "POST" },
      ),
    onSuccess: (value, id) => {
      setDelivered((current) => ({ ...current, [id]: value }));
      client.invalidateQueries({ queryKey: ["visit-verification-customer"] });
    },
  });
  return (
    <section className="mt-8" aria-labelledby="customer-visit-verification-heading">
      <h2 id="customer-visit-verification-heading" className="text-2xl font-bold">
        Visit Verification
      </h2>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        {query.data?.map((item) => {
          const state = item.visit_verification;
          const delivery = delivered[item.id];
          return (
            <article key={item.id} className="min-w-0 rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div><h3 className="font-bold">{item.therapy_name}</h3><p className="text-sm">{new Date(item.scheduled_start).toLocaleString()}</p></div>
                <StatusBadge value={state} />
              </div>
              {state.status === "VERIFIED" ? (
                <p className="mt-4 font-semibold">✓ Verified · Check-in verified{state.verified_at ? ` · ${new Date(state.verified_at).toLocaleString()}` : ""}</p>
              ) : state.status === "AWAITING_VERIFICATION" ? (
                <>
                  {delivery ? (
                    <><p aria-label="Visit OTP" className="mt-4 break-all text-center font-mono text-3xl font-bold tracking-[0.2em]">{delivery.otp}</p><p className="mt-2 text-sm">Expires {delivery.expires_at ? new Date(delivery.expires_at).toLocaleString() : "soon"}.</p></>
                  ) : (
                    <button type="button" onClick={() => issue.mutate(item.id)} disabled={issue.isPending} className="mt-4 min-h-11 w-full rounded-xl bg-emerald-700 px-4 font-bold text-white">{issue.isPending ? "Generating…" : "Generate Visit OTP"}</button>
                  )}
                  <p className="mt-3 text-sm font-semibold">Share this OTP only after your assigned JeevaSetu Physiotherapist reaches your location.</p>
                </>
              ) : (
                <p className="mt-4 text-sm">Visit OTP will become available when your confirmed visit is ready.</p>
              )}
              {state.status === "EXPIRED" && <button type="button" onClick={() => issue.mutate(item.id)} className="mt-3 min-h-11 w-full rounded-xl border border-emerald-700 font-bold">Generate a new Visit OTP</button>}
              {state.status === "LOCKED" && <p className="mt-3 font-semibold text-red-700">Too many attempts. Verification is locked.</p>}
              {issue.isError && <p role="alert" className="mt-2 text-red-700">{issue.error.message}</p>}
            </article>
          );
        })}
      </div>
    </section>
  );
}
