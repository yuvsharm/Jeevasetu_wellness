"use client";

import Image from "next/image";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { requestJson } from "@/lib/api/client";
import type { OperationalAppointment } from "@/lib/appointments/contracts";

const declineReasons = [
  "unavailable",
  "schedule conflict",
  "too far",
  "outside expertise",
  "emergency/personal",
  "other",
];
const OWNER_UPI_ID = "7351150555@ptsbi";
const OWNER_QR_PATH = "/images/payments/jeevasetu-owner-upi-qr.png";

export function PractitionerVisitWorkflow() {
  const client = useQueryClient();
  const [decline, setDecline] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);
  const [therapyDelivered, setTherapyDelivered] = useState(false);
  const [paymentReceived, setPaymentReceived] = useState(false);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">("idle");

  const query = useQuery({
    queryKey: ["assigned-appointments"],
    queryFn: () => requestJson<OperationalAppointment[]>("/api/schedule/assigned-to-me"),
    refetchInterval: 10_000,
  });
  const refresh = () => client.invalidateQueries({ queryKey: ["assigned-appointments"] });
  const respond = useMutation({
    mutationFn: (value: { id: string; accept: boolean; reason?: string }) =>
      requestJson(`/api/schedule/${value.id}/assignment-response`, {
        method: "POST",
        body: JSON.stringify(value),
      }),
    onSuccess: () => {
      setDecline(null);
      setReason("");
      refresh();
    },
  });
  const journey = useMutation({
    mutationFn: (id: string) =>
      requestJson(`/api/schedule/${id}/journey`, {
        method: "POST",
        body: JSON.stringify({ journey_status: "EN_ROUTE" }),
      }),
    onSuccess: refresh,
  });
  const lifecycle = useMutation({
    mutationFn: (value: { id: string; status: "IN_PROGRESS" }) =>
      requestJson(`/api/schedule/${value.id}/status`, {
        method: "POST",
        body: JSON.stringify({ status: value.status }),
      }),
    onSuccess: refresh,
  });
  const completion = useMutation({
    mutationFn: (id: string) =>
      requestJson(`/api/schedule/${id}/complete-and-confirm-payment`, {
        method: "POST",
        body: JSON.stringify({ therapy_delivered: true, payment_received: true }),
      }),
    onSuccess: () => {
      setConfirming(null);
      setTherapyDelivered(false);
      setPaymentReceived(false);
      refresh();
    },
  });

  const openConfirmation = (id: string) => {
    setTherapyDelivered(false);
    setPaymentReceived(false);
    setConfirming(id);
  };
  const copyUpiId = async () => {
    try {
      if (!navigator.clipboard) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(OWNER_UPI_ID);
      setCopyState("copied");
    } catch {
      setCopyState("error");
    }
  };

  const items =
    query.data?.slice().sort((a, b) => Date.parse(a.scheduled_start) - Date.parse(b.scheduled_start)) ??
    [];

  const render = (item: OperationalAppointment) => {
    const completed = item.status === "COMPLETED";
    const paid = item.payment_status === "PAID";
    return (
      <article key={item.id} className="min-w-0 rounded-2xl border bg-white p-4 sm:p-5">
        <p className="text-xs font-semibold text-emerald-800">
          Booking {item.id.slice(0, 8).toUpperCase()} ·{" "}
          {completed ? "APPOINTMENT COMPLETED" : item.status.replaceAll("_", " ")}
        </p>
        <h3 className="font-bold">
          {item.assignment_status === "PENDING"
            ? "New Service Request"
            : item.assignment_status === "REJECTED"
              ? "Rejected assignment"
              : item.patient_name}
        </h3>
        <p>
          {(item.requested_therapy_names?.length
            ? item.requested_therapy_names
            : [item.therapy_name]
          ).join(", ")}{" "}
          · {item.duration_minutes} minutes
        </p>
        <p>
          {new Date(item.scheduled_start).toLocaleString()} · {item.city || "Service area pending"}
        </p>

        {item.assignment_status === "PENDING" ? (
          <div className="mt-4 flex flex-wrap gap-2">
            <button onClick={() => respond.mutate({ id: item.id, accept: true })} className="button-primary">
              Accept Appointment
            </button>
            <button onClick={() => setDecline(item.id)} className="button-secondary text-red-700">
              Decline
            </button>
          </div>
        ) : item.assignment_status === "REJECTED" ? (
          <p className="mt-4 rounded-xl bg-red-50 p-3">{item.assignment_rejection_reason}</p>
        ) : (
          item.assignment_status === "ACCEPTED" && (
            <>
              <dl className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
                <Info label="Customer" value={`${item.patient_name} · ${item.patient_age ?? "Age unavailable"}`} />
                <Info label="Contact" value={item.patient_mobile || "Not provided"} />
                <Info
                  label="Service address"
                  value={[
                    item.address_line_1,
                    item.address_line_2,
                    item.landmark,
                    item.city,
                    item.region,
                    item.pin_code,
                  ]
                    .filter(Boolean)
                    .join(", ")}
                />
                <Info
                  label="Status"
                  value={
                    completed
                      ? "Appointment completed successfully"
                      : item.status === "IN_PROGRESS"
                        ? "THERAPY IN PROGRESS"
                        : item.journey_status === "EN_ROUTE"
                          ? "EN ROUTE"
                          : "THERAPIST ACCEPTED"
                  }
                />
              </dl>
              <div className="mt-4 flex flex-wrap gap-2">
                {item.status === "CONFIRMED" && item.journey_status === "NOT_STARTED" && (
                  <button onClick={() => journey.mutate(item.id)} className="button-primary">
                    En Route
                  </button>
                )}
                {item.status === "CONFIRMED" && item.journey_status === "EN_ROUTE" && (
                  <button
                    onClick={() => lifecycle.mutate({ id: item.id, status: "IN_PROGRESS" })}
                    className="button-primary"
                  >
                    Start Session
                  </button>
                )}
              </div>

              {completed ? (
                <section
                  aria-label="Completed appointment payment"
                  className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4"
                >
                  <p className="font-bold text-emerald-900">
                    {paid
                      ? "Appointment completed successfully · Payment confirmed"
                      : "Treatment completed successfully"}
                  </p>
                  <p className="mt-1">Amount: {formatAmount(item.payment_amount_due)}</p>
                  <p className="font-semibold">{paid ? "Payment confirmed" : "Payment pending"}</p>
                  {item.payment_paid_at && (
                    <p className="mt-1 text-sm text-slate-600">
                      Confirmed {new Date(item.payment_paid_at).toLocaleString()}
                    </p>
                  )}
                </section>
              ) : (
                <PaymentToOwner
                  item={item}
                  copyState={copyState}
                  onCopy={copyUpiId}
                  onConfirm={() => openConfirmation(item.id)}
                  confirmationPending={completion.isPending}
                />
              )}
            </>
          )
        )}
      </article>
    );
  };

  return (
    <section className="mt-8">
      <h2 className="text-2xl font-bold">My Appointments</h2>
      <p className="text-slate-600">Only the next valid service action is available.</p>
      <h3 className="mt-5 text-xl font-bold">Upcoming and active</h3>
      <div className="mt-3 grid gap-4 lg:grid-cols-2">
        {items.filter((item) => item.status !== "COMPLETED").map(render)}
      </div>
      <h3 className="mt-7 text-xl font-bold">Completed Appointments</h3>
      <div className="mt-3 grid gap-4 lg:grid-cols-2">
        {items.filter((item) => item.status === "COMPLETED").map(render)}
      </div>

      {decline && (
        <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              respond.mutate({ id: decline, accept: false, reason });
            }}
            className="w-full max-w-md rounded-2xl bg-white p-6"
          >
            <h3 className="text-xl font-bold">Reject service request</h3>
            <label className="mt-4 grid gap-2">
              Reason
              <select
                required
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                className="min-h-12 rounded-xl border px-3"
              >
                <option value="">Select</option>
                {declineReasons.map((value) => <option key={value}>{value}</option>)}
              </select>
            </label>
            <div className="mt-4 flex gap-2">
              <button disabled={!reason || respond.isPending} className="button-primary">
                Confirm rejection
              </button>
              <button type="button" onClick={() => setDecline(null)} className="button-secondary">
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {confirming && (
        <div role="dialog" aria-modal="true" aria-labelledby="completion-dialog-title" className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white p-5 shadow-2xl sm:p-6">
            <h3 id="completion-dialog-title" className="text-xl font-bold">
              Confirm completion and payment
            </h3>
            <p className="mt-2 text-slate-700">
              Confirm that the therapy has been completed and the customer has shown successful payment.
            </p>
            <div className="mt-5 grid gap-3">
              <label className="flex min-h-12 items-start gap-3 rounded-xl border p-3 font-semibold">
                <input
                  type="checkbox"
                  checked={therapyDelivered}
                  onChange={(event) => setTherapyDelivered(event.target.checked)}
                  className="mt-1 size-5"
                />
                Therapy/service was delivered
              </label>
              <label className="flex min-h-12 items-start gap-3 rounded-xl border p-3 font-semibold">
                <input
                  type="checkbox"
                  checked={paymentReceived}
                  onChange={(event) => setPaymentReceived(event.target.checked)}
                  className="mt-1 size-5"
                />
                Customer showed successful owner payment confirmation
              </label>
            </div>
            <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={() => setConfirming(null)}
                disabled={completion.isPending}
                className="button-secondary"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => completion.mutate(confirming)}
                disabled={!therapyDelivered || !paymentReceived || completion.isPending}
                className="button-primary"
              >
                {completion.isPending ? "Confirming…" : "Confirm Completion & Payment"}
              </button>
            </div>
          </div>
        </div>
      )}

      {(respond.error || journey.error || lifecycle.error || completion.error) && (
        <p role="alert" className="mt-4 text-red-700">
          {(respond.error || journey.error || lifecycle.error || completion.error)?.message}
        </p>
      )}
    </section>
  );
}

function PaymentToOwner({
  item,
  copyState,
  onCopy,
  onConfirm,
  confirmationPending,
}: {
  item: OperationalAppointment;
  copyState: "idle" | "copied" | "error";
  onCopy: () => void;
  onConfirm: () => void;
  confirmationPending: boolean;
}) {
  return (
    <section
      aria-label="Payment to JeevaSetu owner"
      className="mt-5 rounded-2xl border border-sky-200 bg-sky-50 p-3 sm:p-5"
    >
      <h4 className="text-lg font-bold text-slate-950">Payment to JeevaSetu / Owner</h4>
      <p className="mt-1 text-sm text-slate-700">
        Ask the customer to pay the owner directly and show the successful payment confirmation.
      </p>
      <p className="mt-3 text-xl font-black text-emerald-900">
        Amount: {formatAmount(item.payment_amount_due)}
      </p>
      <div className="mt-4 flex justify-center rounded-2xl bg-white p-1 sm:p-3">
        <Image
          src={OWNER_QR_PATH}
          alt="JeevaSetu owner UPI payment QR code"
          width={1012}
          height={1601}
          loading="eager"
          unoptimized
          className="h-auto w-full max-w-80 object-contain"
          sizes="(max-width: 640px) calc(100vw - 4rem), 20rem"
        />
      </div>
      <div className="mt-4 rounded-xl bg-white p-3">
        <span className="block text-xs font-bold uppercase tracking-wide text-slate-500">Owner UPI ID</span>
        <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
          <code className="break-all text-base font-bold text-slate-950">{OWNER_UPI_ID}</code>
          <button type="button" onClick={onCopy} className="min-h-11 rounded-xl border border-emerald-700 px-4 font-bold text-emerald-800">
            Copy UPI ID
          </button>
        </div>
        {copyState === "copied" && <p role="status" className="mt-1 text-sm font-semibold text-emerald-800">UPI ID copied.</p>}
        {copyState === "error" && <p role="alert" className="mt-1 text-sm text-red-700">Copy is unavailable. Select the UPI ID above.</p>}
      </div>
      <p className="mt-3 text-sm font-semibold text-amber-900">
        Displaying this QR does not confirm payment.
      </p>
      {item.status === "IN_PROGRESS" && (
        <button
          type="button"
          onClick={onConfirm}
          disabled={confirmationPending}
          className="button-primary mt-4 w-full"
        >
          Complete Therapy & Confirm Payment
        </button>
      )}
    </section>
  );
}

function formatAmount(amount?: string | null) {
  return amount ? `₹${amount}` : "Amount unavailable";
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-bold">{label}</dt>
      <dd className="break-words">{value}</dd>
    </div>
  );
}
