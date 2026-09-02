import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CustomerOffersPage from "@/app/(protected)/customer/offers/page";

vi.mock("@/components/auth/protected-page", () => ({
  ProtectedPage: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

const publicOffer = {
  id: "offer-1", title: "Active Wellness Test Offer", promotional_text: "Save on selected care",
  offer_type: "PERCENTAGE", eligible_therapies: ["therapy-1"], eligible_therapy_names: ["Kati Basti"],
  minimum_therapy_count: 1,
  discount_value: "10.00", fixed_price: null, free_therapy: null, free_therapy_name: "", free_quantity: 1,
  valid_from: "2026-08-31T00:00:00Z", valid_until: "2026-09-02T00:00:00Z",
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
});
