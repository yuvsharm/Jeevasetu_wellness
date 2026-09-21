import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { PractitionerVisitWorkflow } from "./practitioner-visit-workflow";

const appointment = {
  id: "visit-1", patient_name: "Meera Relative", patient_age: 67,
  patient_mobile: "+919876543210", therapy_name: "Physiotherapy",
  requested_therapy_names: ["Physiotherapy", "Kati Basti"], duration_minutes: 60,
  scheduled_start: "2026-08-12T10:00:00Z", address_line_1: "163 C Block",
  address_line_2: "First floor", landmark: "Near park", city: "Meerut",
  region: "Uttar Pradesh", pin_code: "250004", assignment_status: "PENDING",
  status: "SCHEDULED", journey_status: "NOT_STARTED",
};

function mount() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><PractitionerVisitWorkflow /></QueryClientProvider>);
}

afterEach(() => vi.restoreAllMocks());

it("keeps assigned cards compact and reveals scrollable authorized details", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify([appointment]), { status: 200 }));
  mount();
  expect(await screen.findByRole("heading", { name: "Meera Relative" })).toBeInTheDocument();
  expect(screen.queryByText("+919876543210")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "See More / View Details" }));
  expect(screen.getByText("+919876543210")).toBeInTheDocument();
  expect(screen.getByText("163 C Block, First floor, Near park, Meerut, Uttar Pradesh, 250004")).toBeInTheDocument();
  expect(screen.getByText("Registered contact").closest("dl")).toHaveClass("overflow-y-auto");
});

it("shows only Therapy Done for a prepaid active visit and prevents duplicate submission", async () => {
  const active = { ...appointment, assignment_status: "ACCEPTED", status: "IN_PROGRESS", journey_status: "REACHED", payment_status: "PAID", payment_amount_due: "1777.00" };
  const completed = { ...active, status: "COMPLETED" };
  let current = active;
  let resolveCompletion!: (response: Response) => void;
  const pending = new Promise<Response>((resolve) => { resolveCompletion = resolve; });
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    if (init?.method === "POST" && String(input).endsWith("/complete-and-confirm-payment")) return pending;
    return new Response(JSON.stringify([current]), { status: 200 });
  });
  mount();
  const done = await screen.findByRole("button", { name: "Therapy Done" });
  expect(screen.queryByRole("button", { name: /Payment QR/ })).not.toBeInTheDocument();
  expect(screen.queryByText(/payment confirmation/i)).not.toBeInTheDocument();
  await userEvent.click(done);
  await userEvent.click(done);
  expect(fetchMock.mock.calls.filter(([input, init]) => String(input).endsWith("/complete-and-confirm-payment") && init?.method === "POST")).toHaveLength(1);
  expect(fetchMock).toHaveBeenCalledWith("/api/schedule/visit-1/complete-and-confirm-payment", expect.objectContaining({ body: JSON.stringify({ therapy_delivered: true }) }));
  current = completed;
  resolveCompletion(new Response(JSON.stringify(completed), { status: 200 }));
  expect(await screen.findByText("Therapy completed")).toBeInTheDocument();
});

it("keeps the paid prepaid visit active when Therapy Done fails", async () => {
  const active = { ...appointment, assignment_status: "ACCEPTED", status: "IN_PROGRESS", journey_status: "REACHED", payment_status: "PAID" };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    if (init?.method === "POST" && String(input).endsWith("/complete-and-confirm-payment")) throw new TypeError("offline");
    return new Response(JSON.stringify([active]), { status: 200 });
  });
  mount();
  await userEvent.click(await screen.findByRole("button", { name: "Therapy Done" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("The service is unavailable");
  expect(screen.getByRole("button", { name: "Therapy Done" })).toBeInTheDocument();
});
