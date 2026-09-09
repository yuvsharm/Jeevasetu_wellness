import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PractitionerReview } from "./manager-review";

const application = { id: "app-1", status: "SUBMITTED", category: "PHYSIOTHERAPIST", full_legal_name: "Applicant One", highest_qualification: "BPT", qualification_title: "", experience_years: 3, experience_months: 2, city: "Meerut", state: "Uttar Pradesh", documents: [], competencies: [], has_profile_photo: false, submitted_at: "2026-08-12T09:00:00Z", date_of_birth: "1990-01-01", gender: "FEMALE", email: "one@example.com", mobile_number: "+919876543210", current_address: "Meerut", specialization: "", college_institute: "College", awarding_body: "University", passing_year: 2012, registration_number: "", recent_organization: "", has_home_service_experience: true, previous_experience: "", service_area_names: ["Meerut"], working_days: [0], working_hours_start: "09:00:00", working_hours_end: "17:00:00", availability_notes: "", bio: "Professional bio", correction_reason: "", rejection_reason: "" };
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
    renderReview(); await userEvent.click(await screen.findByRole("button", { expanded: false })); await userEvent.click(screen.getByRole("button", { name: "Start Review" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/practitioners/applications/app-1/review", expect.objectContaining({ method: "POST", body: JSON.stringify({ action: "review", reason: "" }) })));
    expect(await screen.findByRole("status")).toHaveTextContent("Under review");
    expect((await screen.findAllByText("Under review")).length).toBeGreaterThan(0);
    expect(screen.getByRole("status")).toHaveTextContent("Owner Reviewer");
  });
  it("shows Django list validation and sends the exact approval contract", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => init?.method === "POST"
      ? new Response(JSON.stringify(["At least one therapy must be selected before approval."]), { status: 400 })
      : new Response(JSON.stringify([{ ...application, status: "UNDER_REVIEW" }]), { status: 200 }));
    renderReview();
    await userEvent.click(await screen.findByRole("button", { expanded: false }));
    expect(await screen.findByRole("note")).toHaveTextContent("a verified Government ID, and a verified qualification document");
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/practitioners/applications/app-1/review", expect.objectContaining({ method: "POST", body: JSON.stringify({ action: "approve", reason: "" }) })));
    expect(await screen.findByRole("alert")).toHaveTextContent("At least one therapy must be selected before approval.");
  });
  it("shows therapies without verification language and removes one through the therapy endpoint", async () => {
    const current = { ...application, status: "UNDER_REVIEW", competencies: [{ id: "competency-1", therapy: "therapy-1", therapy_name: "Abhyang", experience_months: 0, verification_status: "PENDING" }] };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => init?.method === "DELETE"
      ? new Response(null, { status: 204 })
      : new Response(JSON.stringify([current]), { status: 200 }));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderReview();
    await userEvent.click(await screen.findByRole("button", { expanded: false }));
    expect(screen.getByText("Abhyang")).toBeInTheDocument();
    expect(screen.queryByText("Pending Verification")).not.toBeInTheDocument();
    expect(screen.queryByText("✓ Verified")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Remove Abhyang" }));
    expect(window.confirm).toHaveBeenCalledWith("Remove Abhyang from this practitioner's therapies?");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/practitioners/competencies/competency-1", expect.objectContaining({ method: "DELETE" })));
  });
  it.each([["Request Correction", "correction"], ["Reject", "reject"]])("requires a reason for %s", async (label, action) => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => init?.method === "POST" ? new Response(JSON.stringify({ ...application, status: action === "reject" ? "REJECTED" : "CORRECTION_REQUIRED", reviewer_name: "Owner Reviewer", reviewed_at: "2026-08-13T10:00:00Z", ...(action === "reject" ? { rejection_reason: "Evidence needs clarification" } : { correction_reason: "Evidence needs clarification" }) }), { status: 200 }) : new Response(JSON.stringify([{ ...application, status: "UNDER_REVIEW" }]), { status: 200 }));
    renderReview(); await userEvent.click(await screen.findByRole("button", { expanded: false })); await userEvent.click(screen.getByRole("button", { name: label }));
    const reason = screen.getByLabelText("Reason"); const confirm = screen.getByRole("button", { name: "Confirm" }); expect(confirm).toBeDisabled();
    await userEvent.type(reason, "Evidence needs clarification"); await userEvent.click(confirm);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/practitioners/applications/app-1/review", expect.objectContaining({ body: JSON.stringify({ action, reason: "Evidence needs clarification" }) })));
    expect(await screen.findByRole("status")).toHaveTextContent("Owner Reviewer");
    expect(screen.getByRole("status")).toHaveTextContent("Reason: Evidence needs clarification");
  });
});
