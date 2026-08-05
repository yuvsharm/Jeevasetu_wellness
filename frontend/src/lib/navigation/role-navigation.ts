import type { Role } from "@/lib/api/contracts";
import { roleDestinations } from "@/lib/auth/roles";

export type NavigationItem = { label: string; href?: string; unavailable?: boolean };

const future = (labels: string[]): NavigationItem[] => labels.map((label) => ({ label, unavailable: true }));

export const roleNavigation: Record<Role, NavigationItem[]> = {
  OWNER: [
    { label: "Overview", href: roleDestinations.OWNER },
    ...future(["Operations", "Managers", "Physiotherapists", "Customers", "Revenue & Payments", "Therapies & Pricing", "Inventory", "Reports", "Audit Logs", "Settings"]),
  ],
  MANAGER: [
    { label: "Dashboard", href: roleDestinations.MANAGER },
    ...future(["Bookings & Dispatch", "Customers", "Physiotherapists", "Live Operations", "Therapies", "Inventory", "Payment Status", "Complaints", "Reports"]),
    { label: "Profile", href: "/profile" },
  ],
  PHYSIOTHERAPIST: [
    { label: "Dashboard", href: roleDestinations.PHYSIOTHERAPIST },
    ...future(["Today's Visits", "Assigned Patients", "Navigation", "Session Notes", "Attendance", "Availability", "Notifications"]),
    { label: "Profile", href: "/profile" },
  ],
  CUSTOMER: [
    { label: "Dashboard", href: roleDestinations.CUSTOMER },
    ...future(["Book Service", "My Appointments", "My Family", "Treatment Progress", "Packages", "Payments & Invoices", "Notifications", "Support"]),
    { label: "Profile", href: "/profile" },
  ],
};
