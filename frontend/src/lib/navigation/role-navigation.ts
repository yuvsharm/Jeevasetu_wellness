import type { Role } from "@/lib/api/contracts";
import { roleDestinations } from "@/lib/auth/roles";

export type NavigationItem = { label: string; href?: string; unavailable?: boolean };

const future = (labels: string[]): NavigationItem[] => labels.map((label) => ({ label, unavailable: true }));

export const roleNavigation: Record<Role, NavigationItem[]> = {
  OWNER: [
    { label: "Appointment Requests", href: roleDestinations.OWNER },
    { label: "Appointment Schedule", href: roleDestinations.OWNER },
    { label: "Managers & Physiotherapists", href: roleDestinations.OWNER },
    { label: "Patients", href: roleDestinations.OWNER },
    ...future(["Operations", "Revenue & Payments", "Therapies & Pricing", "Inventory", "Reports", "Audit Logs", "Settings"]),
  ],
  MANAGER: [
    { label: "Dashboard", href: roleDestinations.MANAGER },
    { label: "Appointment Schedule", href: roleDestinations.MANAGER },
    { label: "Physiotherapists", href: roleDestinations.MANAGER },
    { label: "Patients", href: roleDestinations.MANAGER },
    { label: "Practitioner Applications", href: roleDestinations.MANAGER },
    ...future(["Bookings & Dispatch", "Live Operations", "Therapies", "Inventory", "Payment Status", "Complaints", "Reports"]),
    { label: "Profile", href: "/profile" },
  ],
  PHYSIOTHERAPIST: [
    { label: "Dashboard", href: roleDestinations.PHYSIOTHERAPIST },
    { label: "My Appointments", href: roleDestinations.PHYSIOTHERAPIST },
    ...future(["Today's Visits", "Assigned Patients", "Navigation", "Session Notes", "Attendance", "Availability", "Notifications"]),
    { label: "Profile", href: "/profile" },
  ],
  CUSTOMER: [
    { label: "My Appointments", href: roleDestinations.CUSTOMER },
    { label: "Book Service", href: "/book-appointment" },
    { label: "Practitioner Application", href: "/practitioner-application" },
    ...future(["My Family", "Treatment Progress", "Packages", "Payments & Invoices", "Notifications", "Support"]),
    { label: "Profile", href: "/profile" },
  ],
};
