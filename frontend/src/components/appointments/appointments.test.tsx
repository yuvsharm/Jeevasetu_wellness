import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BookingForm } from "@/components/appointments/booking-form";
import { CustomerRequests } from "@/components/appointments/customer-requests";
import { OwnerRequests } from "@/components/appointments/owner-requests";
import { SessionProvider } from "@/components/auth/session-provider";
import type { Session } from "@/lib/api/contracts";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/book-appointment",
  useSearchParams: () => new URLSearchParams(),
}));

const customerSession: Session = {
  user: { id: "customer-1", first_name: "Asha", last_name: "Sharma", email: "", mobile_number: "+919999999999", profile_image: "", roles: ["CUSTOMER"] },
  access: { user_id: "customer-1", organization: { id: "org-1", slug: "jeevasetu" }, permitted_clinics: [], roles: [{ id: "role-1", user_id: "customer-1", organization_id: "org-1", clinic_id: null, role: "CUSTOMER", scope: "organization", is_active: true }] },
};

function renderWithQuery(ui: React.ReactNode, withSession = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  if (withSession) client.setQueryData(["session"], customerSession);
  return render(<QueryClientProvider client={client}>{withSession ? <SessionProvider>{ui}</SessionProvider> : ui}</QueryClientProvider>);
}

const therapy = { id: "therapy-kati", name: "Kati Basti", slug: "kati-basti", base_price: "1900.00", default_duration_minutes: 45 };
const catalog = { therapies: [therapy, { ...therapy, id: "therapy-nasya", name: "Nasya", slug: "nasya" }], packages: [], offers: [] };

describe("appointment workflow", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("shows only authenticated booking details and no second OTP", async () => {
    vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      if (String(input) === "/api/commercial/public") return new Response(JSON.stringify(catalog), { status: 200 });
      if (String(input) === "/api/customer/family") return new Response(JSON.stringify([]), { status: 200 });
      if (String(input).startsWith("/api/availability/customer-slots?")) return new Response(JSON.stringify([{ value: "10:00", label: "10:00" }]), { status: 200 });
      return new Response(JSON.stringify({ therapy_ids: [therapy.id], therapy_names: [therapy.name], therapy_prices: {}, package_id: null, package_name: "", offer_id: null, offer_title: "", session_count: 1, regular_amount: "1900.00", discount_amount: "0.00", final_amount: "1900.00", free_benefits: [], duration_minutes: 45 }), { status: 200 });
    });
    renderWithQuery(<BookingForm initialTherapy={therapy.id} />, true);
    expect(await screen.findByRole("heading", { name: /choose care/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/mobile number/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/one-time password|otp/i)).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /kati basti/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("Booking for")).toHaveValue("");
    expect(screen.getByLabelText("Pain area (optional)")).toBeInTheDocument();
  });

  it("preserves therapy selection and submits only the minimal authenticated contract", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/api/commercial/public") return new Response(JSON.stringify(catalog), { status: 200 });
      if (url === "/api/customer/family") return new Response(JSON.stringify([]), { status: 200 });
      if (url === "/api/commercial/quote") return new Response(JSON.stringify({ therapy_ids: [therapy.id], therapy_names: [therapy.name], therapy_prices: {}, package_id: null, package_name: "", offer_id: null, offer_title: "", session_count: 1, regular_amount: "1900.00", discount_amount: "0.00", final_amount: "1900.00", free_benefits: [], duration_minutes: 45 }), { status: 200 });
      if (url.startsWith("/api/availability/customer-slots?")) return new Response(JSON.stringify([{ value: "10:00", label: "10:00" }]), { status: 200 });
      if (url === "/api/appointment-requests") return new Response(JSON.stringify({ id: "request-1", status: "PENDING" }), { status: 201 });
      return new Response(JSON.stringify({}), { status: 200 });
    });
    renderWithQuery(<BookingForm initialTherapy={therapy.id} />, true);
    await screen.findByRole("button", { name: /kati basti/i });
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-09-01" } });
    await screen.findByRole("option", { name: "10:00" });
    fireEvent.change(screen.getByLabelText("Available time slot"), { target: { value: "10:00" } });
    fireEvent.change(screen.getByLabelText("Pain area (optional)"), { target: { value: "Lower back" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm Book Appointment" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/appointment-requests", expect.objectContaining({ method: "POST" })));
    const call = fetchMock.mock.calls.find(([input]) => String(input) === "/api/appointment-requests");
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body).toMatchObject({ therapy: therapy.id, preferred_date: "2026-09-01", preferred_time: "10:00", pain_area: "Lower back" });
    expect(body).not.toHaveProperty("mobile_number");
    expect(body).not.toHaveProperty("booking_verification_token");
    expect(body).not.toHaveProperty("otp");
  });

  it("shows a clear message when clinic hours are not configured", async () => {
    vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/api/commercial/public") return new Response(JSON.stringify(catalog), { status: 200 });
      if (url === "/api/customer/family") return new Response(JSON.stringify([]), { status: 200 });
      if (url.startsWith("/api/availability/customer-slots?")) return new Response(JSON.stringify({ detail: "Online booking is temporarily unavailable because service hours have not been configured. Please contact JeevaSetu.", code: "OPERATING_HOURS_UNAVAILABLE" }), { status: 409 });
      return new Response(JSON.stringify({ therapy_ids: [therapy.id], therapy_names: [therapy.name], final_amount: "1900.00", discount_amount: "0.00", duration_minutes: 45 }), { status: 200 });
    });
    renderWithQuery(<BookingForm initialTherapy={therapy.id} />, true);
    await screen.findByRole("button", { name: /kati basti/i });
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-09-01" } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Online booking is temporarily unavailable because service hours have not been configured. Please contact JeevaSetu.");
  });

  it("renders the owner search and status filters", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    renderWithQuery(<OwnerRequests />);
    expect(screen.getByRole("heading", { name: "Appointment Requests" })).toBeInTheDocument();
    expect(screen.getByLabelText("Search")).toBeInTheDocument();
    expect(screen.getByLabelText("Status")).toBeInTheDocument();
  });

  it("renders the customer request module and booking entry point", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    renderWithQuery(<CustomerRequests />);
    expect(screen.getByRole("heading", { name: "My appointment requests" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Request an appointment" })).toHaveAttribute("href", "/book-appointment");
  });
});
