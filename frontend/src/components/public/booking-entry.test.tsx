import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";

import { BookingEntry } from "./booking-entry";

describe("homepage booking entry", () => {
  it("takes visitors to customer access while preserving the booking intent", () => {
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><BookingEntry /></QueryClientProvider>);
    expect(screen.getByRole("link", { name: /quick appointment/i })).toHaveAttribute("href","/customer-access?returnTo=%2Fbook-appointment");
  });
});
