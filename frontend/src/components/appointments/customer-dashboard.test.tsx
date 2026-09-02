import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CustomerDashboard } from "@/components/appointments/customer-dashboard";

vi.mock("@/components/auth/session-provider", () => ({
  useSession: () => ({ data: { user: { first_name: "Asha", mobile_number: "+910000000000" } } }),
}));
vi.mock("@/components/appointments/customer-rating", () => ({ CustomerRatingPanel: () => null }));

function renderDashboard(requests: unknown[], appointments: unknown[] = [], offers: unknown[] = []) {
  vi.spyOn(global, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url === "/api/appointment-requests") return new Response(JSON.stringify(requests), { status: 200 });
    if (url === "/api/schedule/my-appointments") return new Response(JSON.stringify(appointments), { status: 200 });
    if (url === "/api/commercial/public") return new Response(JSON.stringify({ therapies: [], packages: [], offers }), { status: 200 });
    return new Response(JSON.stringify([]), { status: 200 });
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><CustomerDashboard /></QueryClientProvider>);
}

const pendingRequest = {
  id: "request-1", status: "PENDING", patient_name: "Test patient",
  therapy_name: "Kati Basti", requested_therapy_names: ["Kati Basti"],
  requested_duration_minutes: 45, preferred_date: "2026-09-05", preferred_time: "10:00:00",
  created_at: "2026-08-31T06:12:00Z",
};

describe("CustomerDashboard", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("does not render an empty Pending requests heading", async () => {
    renderDashboard([]);
    expect(await screen.findByText(/welcome, asha/i)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Pending requests" })).not.toBeInTheDocument();
  });

  it("renders pending requests separately when present", async () => {
    renderDashboard([pendingRequest]);
    expect(await screen.findByRole("heading", { name: "Pending requests" })).toBeInTheDocument();
    expect(screen.getByText("Test patient")).toBeInTheDocument();
    expect(screen.getByText("Request Received")).toBeInTheDocument();
    expect(screen.getByText(/Requested on:/)).toBeInTheDocument();
  });

  it("does not present a converted request as a second active booking", async () => {
    renderDashboard([{ ...pendingRequest, status: "APPROVED" }], [{
      id: "appointment-1", originating_request: "request-1", requested_at: pendingRequest.created_at,
      patient_name: "Test patient", therapy_name: "Kati Basti",
      scheduled_start: "2026-09-05T10:00:00+05:30", scheduled_end: "2026-09-05T10:45:00+05:30",
      duration_minutes: 45, status: "SCHEDULED", physiotherapist_name: null,
      assignment_status: "PENDING", payment_status: null,
      visit_verification: { status: "NOT_READY", verified_at: null, expires_at: null, failed_attempt_warning: false },
    }]);
    expect(await screen.findByText("Appointment appointment-1")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Pending requests" })).not.toBeInTheDocument();
    expect(screen.getByText("Requested")).toBeInTheDocument();
  });

  it("shows visit verification only inside an eligible active appointment", async () => {
    renderDashboard([], [{
      id: "appointment-1", patient_name: "Test patient", therapy_name: "Kati Basti",
      scheduled_start: "2026-09-05T10:00:00+05:30", scheduled_end: "2026-09-05T10:45:00+05:30",
      duration_minutes: 45, status: "CONFIRMED", physiotherapist_name: "Dr Asha",
      assignment_status: "ACCEPTED", journey_status: "ARRIVED", payment_status: "PENDING",
      visit_verification: { status: "AWAITING_VERIFICATION", verified_at: null, expires_at: null, failed_attempt_warning: false },
    }]);
    expect(await screen.findByText("Service arrival verification")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate Visit OTP" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Visit Verification" })).not.toBeInTheDocument();
  });

  it("shows a current public offer without technical configuration", async () => {
    renderDashboard([], [], [{
      id: "offer-1", title: "Active Wellness Test Offer", promotional_text: "Save on Kati Basti",
      offer_type: "PERCENTAGE", eligible_therapies: ["therapy-1"], eligible_therapy_names: ["Kati Basti"],
      minimum_therapy_count: 1,
      discount_value: "10.00", fixed_price: null, free_therapy: null, free_therapy_name: "", free_quantity: 1,
      valid_from: "2026-08-31T00:00:00Z", valid_until: "2026-09-02T00:00:00Z",
    }]);
    expect(await screen.findByText("Active Wellness Test Offer")).toBeInTheDocument();
    expect(screen.getByText("10.00% OFF")).toBeInTheDocument();
    expect(screen.getByText("Choose any 1 eligible therapy")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Choose offer" })).toHaveAttribute("href", "/book-appointment?offer=offer-1");
    expect(screen.queryByText(/rule_config|minimum_therapy_count/i)).not.toBeInTheDocument();
  });
});
