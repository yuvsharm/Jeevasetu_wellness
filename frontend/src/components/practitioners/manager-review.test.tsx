import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PractitionerReview } from "./manager-review";

const application = { id: "app-1", status: "SUBMITTED", category: "PHYSIOTHERAPIST", full_legal_name: "Applicant One", highest_qualification: "BPT", experience_years: 3, experience_months: 2, city: "Meerut", state: "Uttar Pradesh", documents: [], competencies: [] };
function renderReview() { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><PractitionerReview /></QueryClientProvider>); }

describe("practitioner review actions", () => {
  it("starts review once and reports the persisted status", async () => {
    let current: typeof application & { reviewer_name?: string; reviewed_at?: string } = application;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      if (init?.method === "POST") {
        current = { ...application, status: "UNDER_REVIEW", reviewer_name: "Owner Reviewer", reviewed_at: "2026-08-12T10:00:00Z" };
        return new Response(JSON.stringify(current), { status: 200 });
      }
      return new Response(JSON.stringify([current]), { status: 200 });
    });
    renderReview(); await userEvent.click(await screen.findByRole("button", { name: "Start Review" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/practitioners/applications/app-1/review", expect.objectContaining({ method: "POST", body: JSON.stringify({ action: "review", reason: "" }) })));
    expect(await screen.findByRole("status")).toHaveTextContent("UNDER REVIEW");
    expect(await screen.findByText("UNDER REVIEW")).toBeInTheDocument();
    expect(screen.getByText("Owner Reviewer")).toBeInTheDocument();
  });
  it("shows Django list validation and sends the exact approval contract", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => init?.method === "POST"
      ? new Response(JSON.stringify(["At least one verified competency is required."]), { status: 400 })
      : new Response(JSON.stringify([application]), { status: 200 }));
    renderReview(); await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/practitioners/applications/app-1/review", expect.objectContaining({ method: "POST", body: JSON.stringify({ action: "approve", reason: "" }) })));
    expect(await screen.findByRole("alert")).toHaveTextContent("At least one verified competency is required.");
  });
  it.each([["Request Correction", "correction"], ["Reject", "reject"]])("requires a reason for %s", async (label, action) => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => init?.method === "POST" ? new Response(JSON.stringify({ ...application, status: action === "reject" ? "REJECTED" : "CORRECTION_REQUIRED" }), { status: 200 }) : new Response(JSON.stringify([application]), { status: 200 }));
    renderReview(); await userEvent.click(await screen.findByRole("button", { name: label }));
    const reason = screen.getByLabelText("Reason"); const confirm = screen.getByRole("button", { name: "Confirm" }); expect(confirm).toBeDisabled();
    await userEvent.type(reason, "Evidence needs clarification"); await userEvent.click(confirm);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/practitioners/applications/app-1/review", expect.objectContaining({ body: JSON.stringify({ action, reason: "Evidence needs clarification" }) })));
  });
});
