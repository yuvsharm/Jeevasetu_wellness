import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";

import { BookingEntry } from "./booking-entry";

describe("homepage booking entry", () => {
  it("takes visitors directly into the quick appointment flow", () => {
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><BookingEntry /></QueryClientProvider>);
    expect(screen.getByRole("link", { name: /quick appointment/i })).toHaveAttribute("href","/book-appointment");
  });
});
