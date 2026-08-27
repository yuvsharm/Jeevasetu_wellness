import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OperatingHoursManagement } from "@/components/availability/operating-hours-management";
import { SessionProvider } from "@/components/auth/session-provider";
import type { Session } from "@/lib/api/contracts";

const session: Session = {
  user: { id: "owner", first_name: "Owner", last_name: "", email: "owner@example.com", mobile_number: null, profile_image: "", roles: ["OWNER"] },
  access: {
    user_id: "owner",
    organization: { id: "org", slug: "jeevasetu" },
    permitted_clinics: [{ id: "clinic-1", slug: "main-clinic" }],
    roles: [{ id: "role", user_id: "owner", organization_id: "org", clinic_id: null, role: "OWNER", scope: "organization", is_active: true }],
  },
};
const days = Array.from({ length: 7 }, (_, weekday) => ({ weekday, is_open: weekday < 6, opens_at: weekday < 6 ? "09:00" : null, closes_at: weekday < 6 ? "18:00" : null }));

describe("operating hours management", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders all weekdays and saves the tenant clinic policy", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockImplementation(async (_input, init) => new Response(JSON.stringify({ clinic: "clinic-1", clinic_name: "Main", timezone: "Asia/Kolkata", configured: true, days }), { status: init?.method === "PUT" ? 200 : 200 }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    client.setQueryData(["session"], session);
    render(<QueryClientProvider client={client}><SessionProvider><OperatingHoursManagement /></SessionProvider></QueryClientProvider>);
    expect(await screen.findByText("Monday")).toBeInTheDocument();
    expect(screen.getByText("Sunday")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save service hours" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/availability/operating-hours/clinic-1", expect.objectContaining({ method: "PUT" })));
  });
});
