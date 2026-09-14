import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { PaymentOperations } from "./payment-operations";

afterEach(() => vi.restoreAllMocks());

it("shows the snapshot amount and lets operations mark payment received", async () => {
  const item = {
    id: "appointment-1",
    physiotherapist_name: "Farha",
    therapy_name: "Abhyang",
    requested_therapy_names: ["Abhyang", "Shirodhara"],
    scheduled_start: "2026-09-15T10:00:00+05:30",
    payment_amount_due: "1900.00",
    payment_status: "PENDING",
  };
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) =>
    new Response(JSON.stringify(init?.method === "POST" ? { ...item, payment_status: "PAID" } : { count: 1, results: [item] }), { status: 200 }),
  );
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><PaymentOperations /></QueryClientProvider>);
  expect(await screen.findByText("Amount due: ₹1900.00")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Payment reference (optional)"), { target: { value: "CASH-42" } });
  fireEvent.click(screen.getByRole("button", { name: "Mark Payment Received" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/schedule/appointment-1/payment", expect.objectContaining({ method: "POST", body: JSON.stringify({ status: "PAID", reference: "CASH-42", note: "" }) })));
});

it("shows therapist confirmation audit details to owner and manager operations", async () => {
  const item = {
    id: "appointment-2",
    patient_name: "Ravi",
    physiotherapist_name: "Farha",
    therapy_name: "Abhyang",
    scheduled_start: "2026-09-15T10:00:00+05:30",
    payment_amount_due: "1900.00",
    payment_status: "PAID",
    payment_paid_at: "2026-09-15T11:00:00+05:30",
    payment_confirmed_by: "Farha Khan",
  };
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ count: 1, next: null, results: [item] }), { status: 200 }),
  );
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><PaymentOperations /></QueryClientProvider>);
  expect(await screen.findByText("Payment: Payment confirmed")).toBeInTheDocument();
  expect(screen.getByText("Confirmed by Farha Khan")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Mark Payment Received" })).not.toBeInTheDocument();
});
