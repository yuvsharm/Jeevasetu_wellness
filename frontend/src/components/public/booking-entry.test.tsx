import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { BookingEntry } from "./booking-entry";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

describe("homepage booking entry", () => {
  it("uses live therapy options and hands selection to the existing booking route", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify([{ id: "therapy-1", name: "Physiotherapy", slug: "physiotherapy" }]), { status: 200 }));
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><BookingEntry /></QueryClientProvider>);
    await screen.findByRole("option", { name: "Physiotherapy" });
    await userEvent.selectOptions(screen.getByLabelText("Service or therapy"), "therapy-1");
    await userEvent.click(screen.getByRole("button", { name: /continue booking/i }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/book-appointment?therapy=therapy-1"));
  });
});
