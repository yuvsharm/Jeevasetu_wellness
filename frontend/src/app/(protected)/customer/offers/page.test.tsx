import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CustomerOffersPage from "@/app/(protected)/customer/offers/page";
import { CustomerDashboard } from "@/components/appointments/customer-dashboard";

vi.mock("@/components/auth/protected-page", () => ({
  ProtectedPage: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

const publicOffer = {
  id: "offer-1", title: "Active Wellness Test Offer", promotional_text: "Save on selected care",
  offer_type: "PERCENTAGE", eligible_therapies: ["therapy-1"], eligible_therapy_names: ["Kati Basti"],
  minimum_therapy_count: 1,
  discount_value: "10.00", fixed_price: null, free_therapy: null, free_therapy_name: "", free_quantity: 1,
  valid_from: null, valid_until: "2099-01-01T00:00:00Z", is_active: true, is_publicly_visible: true,
};

describe("CustomerOffersPage", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders active offers returned by the public commercial API", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({ therapies: [], packages: [], offers: [publicOffer] }), { status: 200 }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><CustomerOffersPage /></QueryClientProvider>);
    expect(await screen.findByRole("heading", { name: "Active Wellness Test Offer" })).toBeInTheDocument();
    expect(screen.getByText("10.00% OFF")).toBeInTheDocument();
    expect(screen.getByText("Choose any 1 eligible therapy")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Choose offer" })).toHaveAttribute("href", "/book-appointment?offer=offer-1");
    expect(screen.queryByText(/rule_config|minimum_therapy_count/i)).not.toBeInTheDocument();
  });

  it.each(["Leg Massage", "Head Massage"])("shows the clean free add-on label for %s", async (name) => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({
      therapies: [], packages: [], offers: [{
        ...publicOffer,
        id: `offer-${name}`,
        title: `Family ${name}`,
        offer_type: "FAMILY_FREE",
        free_therapy: `therapy-${name}`,
        free_therapy_name: name,
      }],
    }), { status: 200 }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><CustomerOffersPage /></QueryClientProvider>);
    expect(await screen.findByText(`Free ${name}`)).toBeInTheDocument();
    expect(screen.queryByText(/therapy-Leg|therapy-Head/)).not.toBeInTheDocument();
  });

  it("shows the same canonical active offer on the customer dashboard and offers page", async () => {
    vi.spyOn(global, "fetch").mockImplementation(async (input) => new Response(JSON.stringify(
      String(input) === "/api/commercial/public"
        ? { therapies: [], packages: [], offers: [publicOffer] }
        : [],
    ), { status: 200 }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><CustomerDashboard /><CustomerOffersPage /></QueryClientProvider>);
    expect(await screen.findAllByRole("heading", { name: "Active Wellness Test Offer" })).toHaveLength(2);
    expect(screen.getByRole("heading", { name: "Current Offers & Packages" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Pending Requests" })).toBeInTheDocument();
  });
});
