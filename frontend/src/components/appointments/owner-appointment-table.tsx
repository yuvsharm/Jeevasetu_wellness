import type { OperationalAppointment } from "@/lib/appointments/contracts";

type Props = {
  items: OperationalAppointment[];
  eligibleOptions: Record<string, string[][] | undefined>;
  assignments: Record<string, string>;
  onAssignmentChange: (id: string, value: string) => void;
  onAssign: (item: OperationalAppointment) => void;
  onUnassign: (item: OperationalAppointment) => void;
  onStatus: (id: string, next: string) => void;
  onAction: (item: OperationalAppointment, action: "detail" | "reschedule" | "cancel" | "audit" | "rebook") => void;
  pendingId?: string;
};

const editableStatuses = ["DRAFT", "PENDING_ASSIGNMENT", "SCHEDULED", "CONFIRMED"];
const finalStatuses = ["COMPLETED", "CANCELLED", "NO_SHOW"];
const label = (value: string) => value.replaceAll("_", " ").toLowerCase().replace(/^./, (letter) => letter.toUpperCase());

export function OwnerAppointmentTable({ items, eligibleOptions, assignments, onAssignmentChange, onAssign, onUnassign, onStatus, onAction, pendingId }: Props) {
  return <div className="mt-5 grid gap-4 xl:grid-cols-2">
    {items.map((item) => {
      const locked = finalStatuses.includes(item.status) || item.status === "IN_PROGRESS";
      const paymentCleared = item.payment_status === "PAID" || item.payment_status == null;
      const needsAssignment = paymentCleared && !locked && (!item.physiotherapist_name || ["UNASSIGNED", "REJECTED"].includes(item.assignment_status));
      const activeAssignment = !locked && Boolean(item.physiotherapist_name) && ["PENDING", "ACCEPTED"].includes(item.assignment_status);
      const options = eligibleOptions[item.id];
      const busy = pendingId === item.id;
      return <article className="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5" key={item.id}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0"><h3 className="break-words text-lg font-bold text-slate-950">{item.patient_name}</h3><p className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-sm">{item.patient_mobile && <a className="font-semibold text-emerald-800 underline" href={`tel:${item.patient_mobile}`}>Call {item.patient_mobile}</a>}{item.patient_email && <a className="break-all text-emerald-800 underline" href={`mailto:${item.patient_email}`}>Email {item.patient_email}</a>}</p></div>
          <span className={`rounded-full px-3 py-1 text-xs font-bold ${item.status === "CANCELLED" ? "bg-red-100 text-red-800" : finalStatuses.includes(item.status) ? "bg-slate-200 text-slate-800" : "bg-emerald-100 text-emerald-900"}`}>{label(item.status)}</span>
        </div>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <div><dt className="font-semibold text-slate-500">Therapy</dt><dd className="break-words">{(item.requested_therapy_names?.length ? item.requested_therapy_names : [item.therapy_name]).join(", ")}</dd></div>
          <div><dt className="font-semibold text-slate-500">Schedule</dt><dd>{new Date(item.scheduled_start).toLocaleString()} · {item.duration_minutes} minutes</dd></div>
          <div className="sm:col-span-2"><dt className="font-semibold text-slate-500">Service address</dt><dd className="break-words">{[item.address_line_1, item.address_line_2, item.landmark, item.city, item.region, item.pin_code].filter(Boolean).join(", ")}</dd></div>
          <div><dt className="font-semibold text-slate-500">Therapist</dt><dd>{item.physiotherapist_name ?? "Not assigned"}</dd></div>
          <div><dt className="font-semibold text-slate-500">Assignment</dt><dd className={item.assignment_status === "REJECTED" ? "font-bold text-amber-800" : ""}>{item.assignment_status === "REJECTED" ? "Assignment declined · Needs reassignment" : label(item.assignment_status)}</dd></div>
          {item.assignment_rejection_reason && <div className="sm:col-span-2"><dt className="font-semibold text-slate-500">Decline reason</dt><dd className="break-words text-amber-800">{item.assignment_rejection_reason}</dd></div>}
          <div><dt className="font-semibold text-slate-500">Payment</dt><dd>{item.payment_status === "PAID" ? "Confirmed" : item.payment_status === "VERIFICATION_PENDING" ? `Verification pending · ₹${item.payment_amount_due}` : item.payment_amount_due ? `Required · ₹${item.payment_amount_due}` : "Historical / not recorded"}</dd></div>
        </dl>
        {!paymentCleared && <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm font-semibold text-amber-950">Therapist assignment is locked until the Owner verifies payment.</div>}
        {needsAssignment && <div className="mt-4 rounded-xl bg-amber-50 p-3"><p className="mb-2 text-sm font-bold text-amber-950">{item.assignment_status === "REJECTED" ? "Assign another therapist" : "Therapist assignment required"}</p><div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]"><select aria-label={`Select therapist for ${item.patient_name}`} value={assignments[item.id] ?? ""} onChange={(event) => onAssignmentChange(item.id, event.target.value)} disabled={busy || options === undefined} className="min-h-11 min-w-0 rounded-lg border bg-white px-3"><option value="">{options === undefined ? "Loading eligible therapists…" : options.length ? "Select eligible therapist" : "No eligible therapist available"}</option>{options?.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select><button type="button" disabled={busy || !assignments[item.id]} className="min-h-11 rounded-lg bg-emerald-700 px-4 font-bold text-white disabled:cursor-not-allowed disabled:opacity-50" onClick={() => onAssign(item)}>{busy ? "Saving…" : item.assignment_status === "REJECTED" ? "Reassign" : "Assign"}</button></div></div>}
        {activeAssignment && <button type="button" disabled={busy} className="mt-4 min-h-11 rounded-lg border border-amber-300 px-4 font-bold text-amber-900 disabled:opacity-50" onClick={() => onUnassign(item)}>{busy ? "Removing…" : "Cancel assignment"}</button>}
        <div className="mt-4 flex flex-wrap gap-2 border-t pt-4"><button className="min-h-11 rounded-lg border px-3 font-bold" onClick={() => onAction(item, "detail")}>View details</button>{item.status === "SCHEDULED" && <button disabled={busy} className="min-h-11 rounded-lg border px-3 font-bold disabled:opacity-50" onClick={() => onStatus(item.id, "CONFIRMED")}>Confirm</button>}{editableStatuses.includes(item.status) && <><button className="min-h-11 rounded-lg border px-3 font-bold" onClick={() => onAction(item, "reschedule")}>Reschedule</button><button className="min-h-11 rounded-lg border border-red-300 px-3 font-bold text-red-700" onClick={() => onAction(item, "cancel")}>Cancel</button></>}{finalStatuses.includes(item.status) && item.originating_request && <button className="min-h-11 rounded-lg border border-emerald-300 px-3 font-bold text-emerald-800" onClick={() => onAction(item, "rebook")}>Book again</button>}<button className="min-h-11 rounded-lg border px-3 font-bold" onClick={() => onAction(item, "audit")}>Audit</button></div>
      </article>;
    })}
    {items.length === 0 && <p className="rounded-2xl border border-dashed bg-white p-5 text-slate-600 xl:col-span-2">No appointments found in this view.</p>}
  </div>;
}
