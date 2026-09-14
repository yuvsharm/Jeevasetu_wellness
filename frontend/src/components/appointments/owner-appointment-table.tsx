import type { OperationalAppointment } from "@/lib/appointments/contracts";

type OwnerAppointmentTableProps = {
  items: OperationalAppointment[];
  staffOptions?: string[][];
  assignments: Record<string, string>;
  onAssignmentChange: (id: string, value: string) => void;
  onAssign: (id: string) => void;
  onUnassign: (id: string) => void;
  onStatus: (id: string, next: string) => void;
  onAction: (
    item: OperationalAppointment,
    action: "detail" | "reschedule" | "cancel" | "audit",
  ) => void;
};

const editableStatuses = ["DRAFT", "PENDING_ASSIGNMENT", "SCHEDULED", "CONFIRMED"];

export function OwnerAppointmentTable({
  items,
  staffOptions,
  assignments,
  onAssignmentChange,
  onAssign,
  onUnassign,
  onStatus,
  onAction,
}: OwnerAppointmentTableProps) {
  return (
    <div className="mt-5 overflow-x-auto rounded-2xl border bg-white">
      <table className="min-w-full text-left text-sm">
        <thead>
          <tr>
            {[
              "Customer",
              "Therapy / address",
              "Schedule",
              "Therapist",
              "Appointment status",
              "Payment",
              "Actions",
            ].map((heading) => <th className="p-4" key={heading}>{heading}</th>)}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr className="border-t align-top" key={item.id}>
              <td className="p-4">
                {item.patient_name}
                <span className="block text-slate-500">{item.patient_identifier}</span>
                {item.originating_request && <span className="block max-w-52 break-all text-xs">Request {item.originating_request}</span>}
              </td>
              <td className="p-4">
                {(item.requested_therapy_names?.length ? item.requested_therapy_names : [item.therapy_name]).join(", ")}
                <span className="block max-w-64 text-slate-600">{item.address_line_1}, {item.city} {item.pin_code}</span>
              </td>
              <td className="p-4">
                {new Date(item.scheduled_start).toLocaleString()}
                <span className="block text-xs">{item.duration_minutes} minutes</span>
              </td>
              <td className="p-4">
                {item.physiotherapist_name ?? "Unassigned"}
                <span className={`block text-xs ${item.assignment_status === "REJECTED" ? "font-bold text-amber-700" : ""}`}>
                  Therapist: {item.assignment_status === "REJECTED" ? "Reassignment required" : item.assignment_status}
                </span>
                <span className="mt-2 flex flex-wrap gap-2">
                  <select
                    aria-label={`Assign ${item.patient_name}`}
                    value={assignments[item.id] ?? ""}
                    onChange={(event) => onAssignmentChange(item.id, event.target.value)}
                    className="min-h-11 rounded-lg border px-2"
                  >
                    <option value="">Select</option>
                    {staffOptions?.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
                  </select>
                  <button type="button" className="min-h-11 font-bold underline" onClick={() => onAssign(item.id)}>Assign</button>
                  {item.physiotherapist_name && <button type="button" className="min-h-11 font-bold text-red-700 underline" onClick={() => onUnassign(item.id)}>Cancel assignment</button>}
                </span>
              </td>
              <td className="p-4">
                <span className="font-semibold">Appointment: {item.status === "COMPLETED" ? "Completed successfully" : item.status}</span>
                {item.assigned_manager_name && <span className="block text-xs">Manager: {item.assigned_manager_name}</span>}
              </td>
              <td className="p-4">
                {item.payment_status === "PAID" ? "Payment confirmed" : item.payment_amount_due ? "Payment pending" : "—"}
                {item.payment_amount_due && <span className="block text-xs">₹{item.payment_amount_due}</span>}
                {item.payment_paid_at && <span className="block text-xs">{new Date(item.payment_paid_at).toLocaleString()}</span>}
                {item.payment_confirmed_by && <span className="block text-xs">Confirmed by {item.payment_confirmed_by}</span>}
              </td>
              <td className="p-4">
                <div className="flex flex-wrap gap-2">
                  <button className="min-h-11 font-bold underline" onClick={() => onAction(item, "detail")}>View details</button>
                  {item.status === "SCHEDULED" && <button className="min-h-11 font-bold underline" onClick={() => onStatus(item.id, "CONFIRMED")}>Confirm</button>}
                  {editableStatuses.includes(item.status) && <>
                    <button className="min-h-11 font-bold underline" onClick={() => onAction(item, "reschedule")}>Reschedule</button>
                    <button className="min-h-11 font-bold text-red-700 underline" onClick={() => onAction(item, "cancel")}>Cancel</button>
                  </>}
                  <button className="min-h-11 font-bold underline" onClick={() => onAction(item, "audit")}>Audit</button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {items.length === 0 && <p className="p-5 text-slate-600">No appointments found.</p>}
    </div>
  );
}
