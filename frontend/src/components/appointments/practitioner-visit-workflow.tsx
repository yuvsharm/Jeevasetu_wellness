"use client";

import Image from "next/image";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

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
  const [paymentQrAppointment, setPaymentQrAppointment] = useState<OperationalAppointment | null>(null);
  const paymentQrCloseRef = useRef<HTMLButtonElement>(null);
  const paymentQrTriggerRef = useRef<HTMLButtonElement | null>(null);
  const completionSubmissionRef = useRef(false);

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
    mutationFn: (value: { id: string; journeyStatus: "EN_ROUTE" | "REACHED" }) =>
      requestJson(`/api/schedule/${value.id}/journey`, {
        method: "POST",
        body: JSON.stringify({ journey_status: value.journeyStatus }),
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
      requestJson<OperationalAppointment>(`/api/schedule/${id}/complete-and-confirm-payment`, {
        method: "POST",
        body: JSON.stringify({ therapy_delivered: true, payment_received: true }),
      }),
    onSuccess: async (updatedAppointment) => {
      client.setQueryData<OperationalAppointment[]>(["assigned-appointments"], (current) =>
        current?.map((item) => item.id === updatedAppointment.id ? updatedAppointment : item),
      );
      setConfirming(null);
      setTherapyDelivered(false);
      setPaymentReceived(false);
      await client.invalidateQueries({ queryKey: ["assigned-appointments"], refetchType: "active" });
    },
    onSettled: () => { completionSubmissionRef.current = false; },
  });

  const openConfirmation = (id: string) => {
    if (completion.isPending || completionSubmissionRef.current) return;
    completion.reset();
    setTherapyDelivered(false);
    setPaymentReceived(false);
    setConfirming(id);
  };
  const submitCompletion = () => {
    if (
      !confirming
      || !therapyDelivered
      || !paymentReceived
      || completion.isPending
      || completionSubmissionRef.current
    ) return;
    completionSubmissionRef.current = true;
    completion.mutate(confirming);
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
  const openPaymentQr = (item: OperationalAppointment, trigger: HTMLButtonElement) => {
    paymentQrTriggerRef.current = trigger;
    setCopyState("idle");
    setPaymentQrAppointment(item);
  };
  const closePaymentQr = () => {
    setPaymentQrAppointment(null);
    window.setTimeout(() => paymentQrTriggerRef.current?.focus(), 0);
  };

  useEffect(() => {
    if (!paymentQrAppointment) return;
    paymentQrCloseRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closePaymentQr();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [paymentQrAppointment]);

  const items =
    query.data?.slice().sort((a, b) => Date.parse(a.scheduled_start) - Date.parse(b.scheduled_start)) ??
    [];

  const render = (item: OperationalAppointment) => {
    const completed = item.status === "COMPLETED";
    const paid = item.payment_status === "PAID";
    const serviceDetailsVisible = item.assignment_status === "PENDING" || item.assignment_status === "ACCEPTED";
    const serviceAddress = [
      item.address_line_1,
      item.address_line_2,
      item.landmark,
      item.city,
      item.region,
      item.pin_code,
    ].filter(Boolean).join(", ");
    return (
      <article key={item.id} className="min-w-0 rounded-2xl border bg-white p-4 sm:p-5">
        <p className="text-xs font-semibold text-emerald-800">
          {completed ? "APPOINTMENT COMPLETED" : item.status.replaceAll("_", " ")}
        </p>
        <h3 className="font-bold">
          {serviceDetailsVisible ? item.patient_name : "Rejected assignment"}
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

        {serviceDetailsVisible && (
          <dl className="mt-4 grid min-w-0 gap-2 text-sm sm:grid-cols-2">
            <Info label="Patient" value={`${item.patient_name}${item.patient_age != null ? ` · Age ${item.patient_age}` : " · Age unavailable"}`} />
            <Info label="Registered contact" value={item.patient_mobile || "Not provided"} />
            <Info label="Service address" value={serviceAddress || "Not provided"} wide />
            <Info
              label="Status"
              value={
                item.assignment_status === "PENDING"
                  ? "AWAITING ACCEPTANCE"
                  : completed
                    ? "Appointment completed successfully"
                    : item.status === "IN_PROGRESS"
                      ? "THERAPY IN PROGRESS"
                      : item.journey_status === "REACHED"
                        ? "REACHED"
                        : item.journey_status === "EN_ROUTE"
                          ? "EN ROUTE"
                          : "THERAPIST ACCEPTED"
              }
            />
          </dl>
        )}

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
              <div className="mt-4 flex flex-wrap gap-2">
                {item.status === "CONFIRMED" && item.journey_status === "NOT_STARTED" && (
                  <button onClick={() => journey.mutate({ id: item.id, journeyStatus: "EN_ROUTE" })} className="button-primary">
                    En Route
                  </button>
                )}
                {item.status === "CONFIRMED" && item.journey_status === "EN_ROUTE" && (
                  <button
                    onClick={() => journey.mutate({ id: item.id, journeyStatus: "REACHED" })}
                    className="button-primary"
                  >
                    Reached
                  </button>
                )}
                {item.status === "CONFIRMED" && item.journey_status === "REACHED" && (
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
                  onShowQr={(trigger) => openPaymentQr(item, trigger)}
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
                  disabled={completion.isPending}
                  onChange={(event) => setTherapyDelivered(event.target.checked)}
                  className="mt-1 size-5"
                />
                Therapy/service was delivered
              </label>
              <label className="flex min-h-12 items-start gap-3 rounded-xl border p-3 font-semibold">
                <input
                  type="checkbox"
                  checked={paymentReceived}
                  disabled={completion.isPending}
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
                onClick={submitCompletion}
                disabled={!therapyDelivered || !paymentReceived || completion.isPending}
                className="button-primary"
              >
                {completion.isPending ? "Confirming…" : "Confirm Completion & Payment"}
              </button>
            </div>
            {completion.isError && <p role="alert" className="mt-3 text-red-700">{completion.error.message === "Something went wrong. Please try again." ? "Completion and payment could not be recorded. Please retry. If the problem continues, contact JeevaSetu support." : completion.error.message}</p>}
          </div>
        </div>
      )}

      {paymentQrAppointment && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="payment-qr-dialog-title"
          className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/50 p-3 sm:p-6"
        >
          <section className="relative my-auto w-full max-w-md rounded-2xl bg-white p-4 shadow-2xl sm:p-6">
            <button
              ref={paymentQrCloseRef}
              type="button"
              aria-label="Close payment QR"
              onClick={closePaymentQr}
              className="absolute right-3 top-3 flex size-11 items-center justify-center rounded-full border bg-white text-2xl font-bold text-slate-700"
            >
              <span aria-hidden="true">×</span>
            </button>
            <h3 id="payment-qr-dialog-title" className="pr-12 text-xl font-bold">Payment to JeevaSetu / Owner</h3>
            <p className="mt-2 text-sm text-slate-600">Scan only for this appointment.</p>
            <p className="mt-3 text-2xl font-black text-emerald-900">Amount: {formatAmount(paymentQrAppointment.payment_amount_due)}</p>
            <div className="mx-auto mt-4 w-full max-w-80 overflow-hidden rounded-2xl bg-white">
              <div className="relative aspect-[1012/1181] w-full overflow-hidden">
                <Image
                  src={OWNER_QR_PATH}
                  alt="JeevaSetu owner UPI payment QR code"
                  width={1012}
                  height={1601}
                  loading="eager"
                  unoptimized
                  className="absolute inset-x-0 h-auto w-full max-w-none"
                  style={{ top: "-35.56%" }}
                  sizes="(max-width: 640px) calc(100vw - 3.5rem), 20rem"
                />
              </div>
            </div>
            <div className="mt-4 rounded-xl bg-slate-50 p-3">
              <span className="block text-xs font-bold uppercase tracking-wide text-slate-500">UPI ID</span>
              <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
                <code className="break-all text-base font-bold text-slate-950">{OWNER_UPI_ID}</code>
                <button type="button" onClick={copyUpiId} className="min-h-11 rounded-xl border border-emerald-700 px-4 font-bold text-emerald-800">Copy</button>
              </div>
              {copyState === "copied" && <p role="status" className="mt-1 text-sm font-semibold text-emerald-800">UPI ID copied.</p>}
              {copyState === "error" && <p role="alert" className="mt-1 text-sm text-red-700">Copy is unavailable. Select the UPI ID above.</p>}
            </div>
            <p className="mt-3 text-sm font-semibold text-amber-900">Opening or scanning this QR does not confirm payment.</p>
          </section>
        </div>
      )}

      {(respond.error || journey.error || lifecycle.error) && (
        <p role="alert" className="mt-4 text-red-700">
          {(respond.error || journey.error || lifecycle.error)?.message}
        </p>
      )}
    </section>
  );
}

function PaymentToOwner({
  item,
  onShowQr,
  onConfirm,
  confirmationPending,
}: {
  item: OperationalAppointment;
  onShowQr: (trigger: HTMLButtonElement) => void;
  onConfirm: () => void;
  confirmationPending: boolean;
}) {
  return (
    <section
      aria-label="Payment to JeevaSetu owner"
      className="mt-5 rounded-2xl border border-sky-200 bg-sky-50 p-3 sm:p-5"
    >
      {item.payment_status === "PAID" ? <p className="font-bold text-emerald-900">Payment confirmed</p> : <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><p className="text-lg font-black text-emerald-900">Payment pending · {formatAmount(item.payment_amount_due)}</p><button type="button" onClick={(event) => onShowQr(event.currentTarget)} className="min-h-11 rounded-xl border border-emerald-700 px-4 font-bold text-emerald-800">Show Payment QR</button></div>}
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

function Info({ label, value, wide = false }: { label: string; value: string; wide?: boolean }) {
  return (
    <div className={wide ? "min-w-0 sm:col-span-2" : "min-w-0"}>
      <dt className="font-bold">{label}</dt>
      <dd className="break-words">{value}</dd>
    </div>
  );
}
