import type { Role } from "@/lib/api/contracts";
import { roleDestinations } from "@/lib/auth/roles";

export type NavigationItem = { label: string; href?: string; unavailable?: boolean };

const future = (labels: string[]): NavigationItem[] => labels.map((label) => ({ label, unavailable: true }));

export const roleNavigation: Record<Role, NavigationItem[]> = {
  OWNER: [
    {label:"Learning Content",href:"/owner/learning"},
    {label:"Credential Reviews",href:"/owner/credentials"},
    { label: "Business Analytics", href: `${roleDestinations.OWNER}#business-analytics` },
    { label: "Appointment Requests", href: `${roleDestinations.OWNER}#appointment-requests` },
    { label: "Appointment Schedule", href: "/owner/appointments" },
    { label: "Book for Customer", href: "/owner/appointments/create" },
    { label: "Physiotherapists", href: `${roleDestinations.OWNER}#staff-management` },
    { label: "Patients", href: `${roleDestinations.OWNER}#patients` },
    { label: "Operating Hours", href: `${roleDestinations.OWNER}#operating-hours` },
    { label: "Therapy Management", href: `${roleDestinations.OWNER}#therapy-management` },
    { label: "Offers & Packages", href: `${roleDestinations.OWNER}#offers-packages` },
    { label: "Customer Reviews", href: `${roleDestinations.OWNER}#customer-reviews` },
    { label: "Practitioner Applications", href: `${roleDestinations.OWNER}#practitioner-applications` },
    { label: "Payments", href: "/owner/payments" },
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
    {label:"Dashboard",href:"/physiotherapist"},
    {label:"My Appointments",href:"/physiotherapist/appointments"},
    {label:"My Profile",href:"/profile"},
    {label:"My Schedule / Time Off",href:"/physiotherapist/schedule"},
    {label:"Learning Centre",href:"/physiotherapist/learning"},
  ],
  CUSTOMER: [
    { label: "My Appointments", href: roleDestinations.CUSTOMER },
    { label: "Book Service", href: "/book-appointment" },
    { label: "Offers & Packages", href: "/customer/offers" },
    { label: "Profile", href: "/profile" },
  ],
};
