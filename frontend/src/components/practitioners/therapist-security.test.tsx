import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { requestJson } from "@/lib/api/client";

import { TherapistSecurity } from "./therapist-security";

vi.mock("@/lib/api/client", () => ({ requestJson: vi.fn() }));
vi.mock("@/lib/auth/msg91-widget", () => ({
  loadOtpWidgetConfig: vi.fn(async () => ({ enabled: false })),
  sendMsg91Otp: vi.fn(),
  verifyMsg91Otp: vi.fn(),
}));

describe("TherapistSecurity", () => {
  beforeEach(() => {
    vi.mocked(requestJson).mockReset();
    vi.mocked(requestJson).mockResolvedValue({ verification_id: "verify-1" });
  });

  it("uses the shared secure OTP input and prevents duplicate issue submissions", async () => {
    render(<TherapistSecurity mobile="9876543210" />);
    fireEvent.click(screen.getByRole("button", { name: "Change Mobile via OTP" }));
    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "Current1!" } });
    fireEvent.change(screen.getByLabelText("New registered mobile"), { target: { value: "9876543211" } });
    const send = screen.getByRole("button", { name: "Send OTP" });
    fireEvent.click(send);
    fireEvent.click(send);

    const input = await screen.findByLabelText("OTP for new mobile");
    expect(input).toHaveAttribute("autocomplete", "one-time-code");
    expect(input).toHaveAttribute("inputmode", "numeric");
    expect(screen.getByText(/••••••3211/)).toBeInTheDocument();
    await waitFor(() => expect(vi.mocked(requestJson)).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button", { name: "Send OTP" })).toBeDisabled();
  });
});
