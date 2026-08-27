import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CustomerPasswordReset } from "./customer-password-reset";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/auth/msg91-widget", () => ({ loadOtpWidgetConfig: vi.fn(async () => ({ enabled: true, widgetId: "present", tokenAuth: "present" })), sendMsg91Otp: vi.fn(async () => undefined), verifyMsg91Otp: vi.fn(async () => "header.payload.signature") }));

describe("customer password reset", () => {
  it("verifies mobile before accepting and submitting a new password", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockImplementation(async (input) => new Response(JSON.stringify(String(input).includes("booking-otp") ? { verification_id: "verification-1" } : { detail: "ok" }), { status: 200 }));
    render(<CustomerPasswordReset />);
    fireEvent.change(screen.getByLabelText("Mobile number"), { target: { value: "9876543210" } });
    fireEvent.click(screen.getByRole("button", { name: "Send OTP" }));
    fireEvent.change(await screen.findByLabelText("One-time password"), { target: { value: "654321" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify mobile" }));
    fireEvent.change(await screen.findByLabelText("New password"), { target: { value: "Replacement-Password-2026!" } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "Replacement-Password-2026!" } });
    fireEvent.click(screen.getByRole("button", { name: "Reset password" }));
    await screen.findByText("Your password has been reset.");
    const call = fetchMock.mock.calls.find(([input]) => String(input) === "/api/session/customer-password-reset");
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body).toMatchObject({ verification_id: "verification-1", mobile_number: "9876543210", access_token: "header.payload.signature", new_password: "Replacement-Password-2026!" });
    expect(body).not.toHaveProperty("otp");
  });
});
