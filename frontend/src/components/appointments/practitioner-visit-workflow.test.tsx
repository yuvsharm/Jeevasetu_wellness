import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PractitionerVisitWorkflow } from "./practitioner-visit-workflow";

const offer = { id: "visit-1", patient_name: "Service request", therapy_name: "Physiotherapy", duration_minutes: 60, scheduled_start: "2026-08-12T10:00:00Z", city: "Meerut", region: "Uttar Pradesh", assignment_status: "PENDING", status: "SCHEDULED", visit_verification: { status: "NOT_READY", verified_at: null, expires_at: null, failed_attempt_warning: false } };
function mount() { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><PractitionerVisitWorkflow /></QueryClientProvider>); }

it("shows a minimal offer and requires a structured decline reason", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => init?.method === "POST" ? new Response(JSON.stringify(offer), { status: 200 }) : new Response(JSON.stringify([offer]), { status: 200 }));
  mount(); expect(await screen.findByText("New Service Request")).toBeInTheDocument(); expect(screen.queryByText(/mobile/i)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Decline" }));
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "Reason" }), "too far");
  await userEvent.click(screen.getByRole("button", { name: "Confirm decline" }));
  expect(fetchMock).toHaveBeenCalledWith("/api/schedule/visit-1/assignment-response", expect.objectContaining({ body: JSON.stringify({ id: "visit-1", accept: false, reason: "too far" }) }));
});
