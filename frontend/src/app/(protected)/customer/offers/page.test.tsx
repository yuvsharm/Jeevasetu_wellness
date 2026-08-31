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
    expect(screen.getByText("Save 10.00%")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Choose offer" })).toHaveAttribute("href", "/book-appointment?offer=offer-1");
    expect(screen.queryByText(/rule_config|minimum_therapy_count/i)).not.toBeInTheDocument();
  });
});
