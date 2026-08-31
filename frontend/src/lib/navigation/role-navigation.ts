import type { Role } from "@/lib/api/contracts";
import { roleDestinations } from "@/lib/auth/roles";

export type NavigationItem = { label: string; href?: string; unavailable?: boolean };

const future = (labels: string[]): NavigationItem[] => labels.map((label) => ({ label, unavailable: true }));

export const roleNavigation: Record<Role, NavigationItem[]> = {
  OWNER: [
    { label: "Business Analytics", href: `${roleDestinations.OWNER}#business-analytics` },
    { label: "Appointment Requests", href: `${roleDestinations.OWNER}#appointment-requests` },
    { label: "Appointment Schedule", href: `${roleDestinations.OWNER}#appointment-schedule` },
    { label: "Managers & Physiotherapists", href: `${roleDestinations.OWNER}#staff-management` },
    { label: "Patients", href: `${roleDestinations.OWNER}#patients` },
    { label: "Operating Hours", href: `${roleDestinations.OWNER}#operating-hours` },
    { label: "Therapy Management", href: `${roleDestinations.OWNER}#therapy-management` },
    { label: "Offers & Packages", href: `${roleDestinations.OWNER}#offers-packages` },
    { label: "Customer Reviews", href: `${roleDestinations.OWNER}#customer-reviews` },
    { label: "Practitioner Applications", href: `${roleDestinations.OWNER}#practitioner-applications` },
    { label: "Visit Verification", href: `${roleDestinations.OWNER}#visit-verification` },
    { label: "Payments", href: `${roleDestinations.OWNER}#payments` },
    { label: "Practitioner Availability", href: `${roleDestinations.OWNER}#availability-management` },
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
    { label: "Offers & Packages", href: "/customer/offers" },
    ...future(["My Family", "Treatment Progress", "Payments & Invoices", "Notifications", "Support"]),
    { label: "Profile", href: "/profile" },
  ],
};
