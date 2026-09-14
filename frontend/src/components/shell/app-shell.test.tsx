import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import type { Session } from "@/lib/api/contracts";
import { AppShell } from "./app-shell";

const navigationState = vi.hoisted(() => ({ pathname: "/manager" }));
vi.mock("next/navigation", () => ({
  usePathname: () => navigationState.pathname,
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

const session: Session = {
  user: { id: "1", first_name: "Maya", last_name: "Manager", email: "", mobile_number: null, profile_image: "", roles: ["MANAGER"] },
  access: {
    user_id: "1",
    organization: { id: "2", slug: "jeevasetu" },
    permitted_clinics: [],
    roles: [{ id: "3", user_id: "1", organization_id: "2", clinic_id: null, role: "MANAGER", scope: "organization", is_active: true }],
  },
};

describe("AppShell", () => {
  it("renders role navigation and marks future modules unavailable", () => {
    render(<AppShell session={session} role="MANAGER" title="Manager dashboard"><p>Content</p></AppShell>);
    expect(screen.getAllByRole("navigation", { name: /manager navigation/i })).toHaveLength(1);
    expect(screen.getAllByText("Bookings & Dispatch")[0].closest("span[aria-disabled]"))
      .toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("Content")).toBeInTheDocument();
  });

  it("opens mobile navigation and the profile menu with keyboard-accessible buttons", async () => {
    render(<AppShell session={session} role="MANAGER" title="Manager dashboard"><p>Content</p></AppShell>);
    await userEvent.click(screen.getByRole("button", { name: "Menu" }));
    expect(screen.getByRole("button", { name: /close navigation/i })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /maya manager/i }));
    expect(screen.getByRole("menuitem", { name: /sign out/i })).toBeInTheDocument();
  });

  it("shows customer offers without practitioner enrollment in customer navigation", () => {
    const customerSession: Session = {
      ...session,
      user: { ...session.user, roles: ["CUSTOMER"] },
      access: { ...session.access, roles: [{ ...session.access.roles[0], role: "CUSTOMER" }] },
    };
    render(<AppShell session={customerSession} role="CUSTOMER" title="My appointments"><p>Content</p></AppShell>);
    expect(screen.getByRole("link", { name: "Offers & Packages" })).toHaveAttribute("href", "/customer/offers");
    expect(screen.queryByText("Practitioner Application")).not.toBeInTheDocument();
  });

  it("scrolls and focuses an owner section without a page navigation", async () => {
    navigationState.pathname = "/owner";
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    const ownerSession: Session = { ...session, user: { ...session.user, roles: ["OWNER"] }, access: { ...session.access, roles: [{ ...session.access.roles[0], role: "OWNER" }] } };
    render(<AppShell session={ownerSession} role="OWNER" title="Owner operations"><section id="staff-management"><h2>Staff Management section</h2></section></AppShell>);
    await userEvent.click(screen.getAllByRole("link", { name: "Physiotherapists" })[0]);
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
    expect(screen.getByRole("heading", { name: /Staff Management section/ })).toHaveFocus();
    expect(screen.getAllByRole("link", { name: "Physiotherapists" })[0]).toHaveAttribute("aria-current", "location");
    navigationState.pathname = "/manager";
  });

  it("links every implemented owner module to a stable /owner anchor", () => {
    navigationState.pathname = "/owner";
    const ownerSession: Session = { ...session, user: { ...session.user, roles: ["OWNER"] }, access: { ...session.access, roles: [{ ...session.access.roles[0], role: "OWNER" }] } };
    render(<AppShell session={ownerSession} role="OWNER" title="Owner operations"><p>Owner content</p></AppShell>);
    const expected = {
      "Appointment Requests": "/owner#appointment-requests",
      "Appointment Schedule": "/owner/appointments",
      "Book for Customer": "/owner/appointments/create",
      Payments: "/owner/payments",
      "Physiotherapists": "/owner#staff-management",
      Patients: "/owner#patients",
      "Operating Hours": "/owner#operating-hours",
      "Therapy Management": "/owner#therapy-management",
      "Offers & Packages": "/owner#offers-packages",
      "Customer Reviews": "/owner#customer-reviews",
      "Practitioner Applications": "/owner#practitioner-applications",
    };
    for (const [label, href] of Object.entries(expected)) expect(screen.getAllByRole("link", { name: label })[0]).toHaveAttribute("href", href);
    navigationState.pathname = "/manager";
  });

  it("honors a direct owner hash after protected content mounts", async () => {
    navigationState.pathname = "/owner";
    window.history.replaceState(null, "", "/owner#offers-packages");
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    const ownerSession: Session = { ...session, user: { ...session.user, roles: ["OWNER"] }, access: { ...session.access, roles: [{ ...session.access.roles[0], role: "OWNER" }] } };
    render(<AppShell session={ownerSession} role="OWNER" title="Owner operations"><section id="offers-packages"><h2>Offers &amp; Packages section</h2></section></AppShell>);
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" }));
    expect(screen.getByRole("heading", { name: "Offers & Packages section" })).toHaveFocus();
    expect(screen.getAllByRole("link", { name: "Offers & Packages" })[0]).toHaveAttribute("aria-current", "location");
    window.history.replaceState(null, "", "/manager");
    navigationState.pathname = "/manager";
  });
});
