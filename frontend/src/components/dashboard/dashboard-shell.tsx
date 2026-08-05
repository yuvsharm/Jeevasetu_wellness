import type { Role } from "@/lib/api/contracts";
import { roleLabels } from "@/lib/auth/roles";

const cards: Record<Role, string[]> = {
  OWNER: ["Business Overview", "Revenue Summary", "Booking Summary", "Therapist Summary", "Inventory Alert", "Reports"],
  MANAGER: ["Today's Bookings", "Unassigned Visits", "Available Physiotherapists", "Delayed Visits", "Low Stock", "Complaints"],
  PHYSIOTHERAPIST: ["Today's Appointments", "Pending Visits", "Completed Visits", "Assigned Patients", "Availability", "Notifications"],
  CUSTOMER: ["Upcoming Appointment", "Active Package", "Assigned Physiotherapist", "Payment Status", "Completed Sessions", "Notifications"],
};

export function DashboardShell({ role }: { role: Role }) {
  return <section aria-labelledby="dashboard-heading"><div className="rounded-2xl border border-emerald-100 bg-emerald-50 p-5"><h2 id="dashboard-heading" className="text-2xl font-bold text-emerald-950">{roleLabels[role]} dashboard shell</h2><p className="mt-2 text-emerald-900">This secure shell is ready. Operational modules and business data are not implemented yet.</p></div><div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{cards[role].map((card) => <article key={card} className="min-h-40 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><div className="h-2 w-16 rounded-full bg-emerald-200" aria-hidden="true" /><h3 className="mt-5 text-lg font-bold text-slate-900">{card}</h3><p className="mt-2 text-sm leading-6 text-slate-600">The underlying module is not implemented yet. No operational data is shown.</p></article>)}</div></section>;
}
