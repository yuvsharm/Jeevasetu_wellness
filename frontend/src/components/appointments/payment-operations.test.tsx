import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { PaymentOperations } from "./payment-operations";

afterEach(() => vi.restoreAllMocks());

it("shows customer-submitted payments and lets the Owner verify once", async () => {
  const item = {
    id: "appointment-1", patient_name: "Asha Sharma", therapy_name: "Abhyang",
    requested_therapy_names: ["Abhyang", "Shirodhara"],
    scheduled_start: "2026-09-15T10:00:00+05:30", payment_amount_due: "1900.00",
    payment_status: "VERIFICATION_PENDING",
  };
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) =>
    new Response(JSON.stringify(init?.method === "POST" ? { ...item, payment_status: "PAID" } : { count: 1, next: null, results: [item] }), { status: 200 }),
  );
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><PaymentOperations /></QueryClientProvider>);
  expect(await screen.findByText("Submitted amount: ₹1900.00")).toBeInTheDocument();
  expect(screen.getByText(/Customer marked “I Have Paid”/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Payment reference (optional)"), { target: { value: "UPI-42" } });
  fireEvent.click(screen.getByRole("button", { name: "Verify Payment & Confirm Booking" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/schedule/appointment-1/payment", expect.objectContaining({ method: "POST", body: JSON.stringify({ status: "PAID", reference: "UPI-42", note: "" }) })));
});

it("requests only verification-pending payments", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ count: 0, next: null, results: [] }), { status: 200 }));
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><PaymentOperations /></QueryClientProvider>);
  expect(await screen.findByText("No payments are awaiting verification.")).toBeInTheDocument();
  expect(String(fetchMock.mock.calls[0]?.[0])).toContain("payment_status=VERIFICATION_PENDING");
});
