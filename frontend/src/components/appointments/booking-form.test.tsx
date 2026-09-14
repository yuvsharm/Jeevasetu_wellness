import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BookingForm } from "./booking-form";

function localToday() {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh: vi.fn() }),
  usePathname: () => "/book-appointment",
  useSearchParams: () => new URLSearchParams("offer=offer-1"),
}));
vi.mock("@/components/auth/session-provider", () => ({
  useSession: () => ({
    data: {
      user: { id: "customer-1" },
      access: { roles: [{ role: "CUSTOMER", is_active: true }] },
    },
    isPending: false,
    error: null,
  }),
}));

const catalog = {
  therapies: [
    { id: "therapy-1", name: "Abhyang", base_price: "1000.00", default_duration_minutes: 60 },
    { id: "therapy-2", name: "Basti", base_price: "700.00", default_duration_minutes: 30 },
    { id: "therapy-3", name: "Shirodhara", base_price: "900.00", default_duration_minutes: 45 },
    { id: "therapy-4", name: "Nasya", base_price: "600.00", default_duration_minutes: 30 },
    { id: "therapy-5", name: "Potli Massage", base_price: "800.00", default_duration_minutes: 45 },
    { id: "therapy-other", name: "Unrelated Therapy", base_price: "500.00", default_duration_minutes: 30 },
    { id: "therapy-addon", name: "Leg Massage", base_price: "0.00", default_duration_minutes: 15, is_offer_free_addon: true },
  ],
  packages: [],
  offers: [{
    id: "offer-1", title: "September saving", promotional_text: "Save now",
    offer_type: "FIXED_DISCOUNT", eligible_therapies: ["therapy-1", "therapy-2", "therapy-3", "therapy-4", "therapy-5"],
    eligible_therapy_names: ["Abhyang", "Basti", "Shirodhara", "Nasya", "Potli Massage"], minimum_therapy_count: 5,
    maximum_therapy_count: null, discount_value: "100.00", fixed_price: null,
    free_therapy: null, free_therapy_name: "", free_quantity: 1, family_required: false,
    minimum_family_members: 1, rule_config: {}, valid_from: "2026-08-30T23:59:00Z", valid_until: "2026-09-15T00:59:00Z",
    is_active: true, is_publicly_visible: true, display_order: 0,
  }],
};
const discountedQuote = {
  therapy_ids: ["therapy-1", "therapy-2", "therapy-3", "therapy-4", "therapy-5"], therapy_names: ["Abhyang", "Basti", "Shirodhara", "Nasya", "Potli Massage"], therapy_prices: { "therapy-1": "1000.00", "therapy-2": "700.00", "therapy-3": "900.00", "therapy-4": "600.00", "therapy-5": "800.00" },
  package_id: null, package_name: "", offer_id: "offer-1", offer_title: "September saving",
  session_count: 1, regular_amount: "1000.00", discount_amount: "100.00", final_amount: "900.00",
  free_benefits: [], duration_minutes: 60,
};

function renderBooking(fetchImplementation: typeof fetch, initialOffer = "offer-1") {
  vi.spyOn(global, "fetch").mockImplementation((input, init) => String(input) === "/api/customer/profile"
    ? Promise.resolve(new Response(JSON.stringify({ address: { address_line_1: "163 C Block", address_line_2: "", landmark: "", city: "Meerut", region: "Uttar Pradesh", pin_code: "250004", latitude: null, longitude: null, location_accuracy_meters: null, location_source: "MANUAL" } })))
    : fetchImplementation(input, init));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><BookingForm initialOffer={initialOffer} initialTherapy={initialOffer ? "" : "therapy-1"} /></QueryClientProvider>);
}

describe("offer booking", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-01T06:00:00+05:30"));
    replace.mockReset();
  });
  afterEach(() => vi.useRealTimers());

  it("prefills only the qualifying therapy count and submits the exact returned slot", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/commercial/public") return new Response(JSON.stringify(catalog));
      if (url === "/api/customer/family") return new Response(JSON.stringify([]));
      if (url.startsWith("/api/availability/customer-slots")) return new Response(JSON.stringify([{ value: "10:00", label: "10:00" }]));
      if (url === "/api/commercial/quote") return new Response(JSON.stringify(discountedQuote));
      if (url === "/api/appointment-requests") return new Response(JSON.stringify({
        id: "request-1", preferred_date: "2026-09-03", preferred_time: "10:00:00", status: "PENDING", created_at: "2026-09-02T10:26:29.750193Z",
      }), { status: 201 });
      return new Response(JSON.stringify({}), { status: 200 });
    });
    renderBooking(fetchMock as typeof fetch);
    expect(await screen.findByRole("button", { name: /Abhyang/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /Basti/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("5 of 5 therapies selected")).toBeInTheDocument();
    const date = screen.getByLabelText("Date");
    expect(date).toHaveAttribute("min", localToday());
    expect(date).toHaveAttribute("max", "2026-09-15");
    fireEvent.change(date, { target: { value: "2026-09-08" } });
    fireEvent.change(await screen.findByLabelText("Available time slot"), { target: { value: "10:00" } });
    const confirm = screen.getByRole("button", { name: "Confirm Book Appointment" });
    await waitFor(() => expect(confirm).toBeEnabled());
    fireEvent.click(confirm);
    expect(await screen.findByText("Booking request submitted successfully.")).toBeInTheDocument();
    expect(screen.getByText("Booking Submitted At")).toBeInTheDocument();
    const createCall = fetchMock.mock.calls.find(([input]) => String(input) === "/api/appointment-requests");
    expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
      therapy: "therapy-1", requested_therapies: ["therapy-2", "therapy-3", "therapy-4", "therapy-5"], selected_offer: "offer-1",
      preferred_date: "2026-09-08", preferred_time: "10:00",
    });
  });

  it("shows live eligible-only progress and does not quote or submit until 5/5 unlocks", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/commercial/public") return new Response(JSON.stringify(catalog));
      if (url === "/api/customer/family") return new Response(JSON.stringify([]));
      if (url === "/api/commercial/quote") return new Response(JSON.stringify(discountedQuote));
      if (url.startsWith("/api/availability/customer-slots")) return new Response(JSON.stringify([]));
      return new Response(JSON.stringify({}), { status: 200 });
    });
    renderBooking(fetchMock as typeof fetch);
    await screen.findByText("5 of 5 therapies selected");

    for (const name of ["Shirodhara", "Nasya", "Potli Massage"]) {
      fireEvent.click(screen.getByRole("button", { name: new RegExp(name) }));
    }
    expect(screen.getByText("2 of 5 therapies selected")).toBeInTheDocument();
    expect(screen.getByText("Select 3 more eligible therapies to unlock this offer.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Unrelated Therapy/ }));
    fireEvent.click(screen.getByRole("button", { name: /Leg Massage/ }));
    expect(screen.getByText("2 of 5 therapies selected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm Book Appointment" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /Shirodhara/ }));
    fireEvent.click(screen.getByRole("button", { name: /Nasya/ }));
    expect(screen.getByText("4 of 5 therapies selected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Potli Massage/ }));
    expect(await screen.findByText("✓ Offer unlocked — ₹100 off applied")).toBeInTheDocument();
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/commercial/quote")).toBe(true));
  });

  it("clears an invalid-date error and ignores its late response after a valid date is selected", async () => {
    let releaseInvalid!: () => void;
    const invalidResponse = new Promise<void>((resolve) => { releaseInvalid = resolve; });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/commercial/public") return new Response(JSON.stringify(catalog));
      if (url === "/api/customer/family") return new Response(JSON.stringify([]));
      if (url.includes("date=2026-09-09")) {
        await invalidResponse;
        return new Response(JSON.stringify({ offer: ["This offer is valid only for appointments from 31 Aug to 15 Sep 2026."] }), { status: 400 });
      }
      if (url.includes("date=2026-09-08")) return new Response(JSON.stringify([{ value: "11:15", label: "11:15" }]));
      if (url === "/api/commercial/quote") {
        return new Response(JSON.stringify(discountedQuote));
      }
      return new Response(JSON.stringify({}), { status: 200 });
    });
    renderBooking(fetchMock as typeof fetch);
    await screen.findByRole("button", { name: /Abhyang/ });
    const date = screen.getByLabelText("Date");
    fireEvent.change(date, { target: { value: "2026-09-09" } });
    fireEvent.change(date, { target: { value: "2026-09-08" } });
    expect(await screen.findByRole("option", { name: "11:15" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Available time slot"), { target: { value: "11:15" } });
    fireEvent.change(date, { target: { value: "2026-09-09" } });
    expect(screen.getByLabelText("Available time slot")).toHaveValue("");
    fireEvent.change(date, { target: { value: "2026-09-08" } });
    releaseInvalid();
    await waitFor(() => expect(screen.queryByText(/not currently available|valid only/i)).not.toBeInTheDocument());
    expect(screen.queryByText("Something went wrong. Please try again.")).not.toBeInTheDocument();
  });

  it("keeps normal calendar behavior when no offer is selected", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/commercial/public") return new Response(JSON.stringify(catalog));
      if (url === "/api/customer/family") return new Response(JSON.stringify([]));
      if (url === "/api/commercial/quote") return new Response(JSON.stringify({ ...discountedQuote, offer_id: null }));
      return new Response(JSON.stringify([]));
    });
    renderBooking(fetchMock as typeof fetch, "");
    await screen.findByRole("button", { name: /Abhyang/ });
    expect(screen.getByLabelText("Date")).toHaveAttribute("min", localToday());
    expect(screen.getByLabelText("Date")).not.toHaveAttribute("max");
  });
});
