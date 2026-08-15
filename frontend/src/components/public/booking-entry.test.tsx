import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { BookingEntry } from "./booking-entry";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

describe("homepage booking entry", () => {
  it("takes visitors directly into the quick appointment flow", async () => {
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><BookingEntry /></QueryClientProvider>);
    const trigger = screen.getByRole("button", { name: /quick appointment/i });
    await userEvent.click(trigger);
    await waitFor(() => expect(push).toHaveBeenCalledWith("/book-appointment"));
  });
});
