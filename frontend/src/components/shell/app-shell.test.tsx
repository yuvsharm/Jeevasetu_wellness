import { render, screen } from "@testing-library/react";
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
    render(<AppShell session={ownerSession} role="OWNER" title="Owner operations"><section id="owner-staff"><h2>Managers &amp; Physiotherapists section</h2></section></AppShell>);
    await userEvent.click(screen.getAllByRole("link", { name: "Managers & Physiotherapists" })[0]);
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
    expect(screen.getByRole("heading", { name: /Managers & Physiotherapists section/ })).toHaveFocus();
    expect(screen.getAllByRole("link", { name: "Managers & Physiotherapists" })[0]).toHaveAttribute("aria-current", "location");
    navigationState.pathname = "/manager";
  });
});
