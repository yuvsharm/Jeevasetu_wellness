import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  CustomerVisitVerificationPanel,
  OperationsVisitVerificationPanel,
  PhysiotherapistVisitVerificationPanel,
} from "@/components/appointments/visit-verification-panels";

const appointment = {
  id: "appointment-1",
  patient_identifier: "PAT-000001",
  patient_name: "Asha Sharma",
  therapy_name: "Physiotherapy",
  clinic_name: "Meerut",
  scheduled_start: "2026-08-08T10:00:00+05:30",
  scheduled_end: "2026-08-08T11:00:00+05:30",
  duration_minutes: 60,
  status: "CONFIRMED",
  physiotherapist_name: "Dr Physio User",
  assignment_status: "ACCEPTED",
  visit_verification: {
    status: "AWAITING_VERIFICATION",
    verified_at: null,
    expires_at: null,
    failed_attempt_warning: false,
  },
};

function wrap(component: React.ReactNode) {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      {component}
    </QueryClientProvider>,
  );
}

describe("visit verification panels", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows operations only safe verification status", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ count: 1, next: null, previous: null, results: [appointment] }),
        { status: 200 },
      ),
    );
    wrap(<OperationsVisitVerificationPanel />);
    expect(await screen.findByText("AWAITING VERIFICATION")).toBeInTheDocument();
    expect(screen.getByText(/OTP values are never available here/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Visit OTP")).not.toBeInTheDocument();
  });

  it("provides the assigned Physiotherapist a six-digit OTP form", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify([appointment]), { status: 200 }),
    );
    wrap(<PhysiotherapistVisitVerificationPanel />);
    expect(await screen.findByLabelText("6-digit Visit OTP")).toHaveAttribute("pattern", "\\d{6}");
    expect(screen.getByRole("button", { name: "Verify Visit" })).toBeInTheDocument();
  });

  it("delivers the OTP only after the Customer explicitly requests it", async () => {
    vi.spyOn(global, "fetch").mockImplementation(async (_input, init) => {
      if (init?.method === "POST") {
        return new Response(
          JSON.stringify({ otp: "482913", expires_at: "2026-08-08T10:15:00+05:30" }),
          { status: 201 },
        );
      }
      return new Response(JSON.stringify([appointment]), { status: 200 });
    });
    wrap(<CustomerVisitVerificationPanel />);
    const button = await screen.findByRole("button", { name: "Generate Visit OTP" });
    expect(screen.queryByLabelText("Visit OTP")).not.toBeInTheDocument();
    fireEvent.click(button);
    await waitFor(() => expect(screen.getByLabelText("Visit OTP")).toHaveTextContent("482913"));
    expect(screen.getByText(/Share this OTP only after/)).toBeInTheDocument();
  });
});
