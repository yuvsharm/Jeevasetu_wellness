import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CustomerRegistration } from "./customer-registration";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams("returnTo=%2Fbook-appointment%3Ftherapy%3Dtherapy-1"),
}));
vi.mock("@/lib/auth/msg91-widget", () => ({
  loadOtpWidgetConfig: vi.fn(async () => ({ enabled: true, widgetId: "present", tokenAuth: "present" })),
  sendMsg91Otp: vi.fn(async () => undefined),
  verifyMsg91Otp: vi.fn(async () => "header.payload.signature"),
}));

describe("customer registration", () => {
  beforeEach(() => { vi.restoreAllMocks(); replace.mockClear(); });

  it("creates the customer only after MSG91 verification and resumes booking", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      if (String(input) === "/api/booking-otp/issue") return new Response(JSON.stringify({ verification_id: "verification-1" }), { status: 201 });
      if (String(input) === "/api/session/customer-register") return new Response(JSON.stringify({ user: { id: "customer-1" } }), { status: 201 });
      return new Response(JSON.stringify({}), { status: 200 });
    });
    render(<CustomerRegistration />);
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Asha Sharma" } });
    fireEvent.change(screen.getByLabelText("Age"), { target: { value: "34" } });
    fireEvent.change(screen.getByLabelText("Gender"), { target: { value: "FEMALE" } });
    fireEvent.change(screen.getByLabelText("Mobile number"), { target: { value: "9876543210" } });
    fireEvent.change(screen.getByLabelText("Email (optional)"), { target: { value: "asha@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "Asha-Strong-Password-2026!" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "Asha-Strong-Password-2026!" } });
    fireEvent.change(screen.getByLabelText("Address"), { target: { value: "163 C Block" } });
    fireEvent.change(screen.getByLabelText("PIN code"), { target: { value: "250004" } });
    fireEvent.click(screen.getByRole("button", { name: "Send OTP" }));
    await screen.findByLabelText("One-time password");
    expect(fetchMock.mock.calls.filter(([input]) => String(input) === "/api/session/customer-register")).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("One-time password"), { target: { value: "654321" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify and create account" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/book-appointment?therapy=therapy-1"));
    const call = fetchMock.mock.calls.find(([input]) => String(input) === "/api/session/customer-register");
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body).toMatchObject({ verification_id: "verification-1", access_token: "header.payload.signature", full_name: "Asha Sharma", email: "asha@example.com", password: "Asha-Strong-Password-2026!", confirm_password: "Asha-Strong-Password-2026!", age: 34, gender: "FEMALE" });
    expect(body).not.toHaveProperty("authkey");
  });

  it("does not send OTP when passwords differ", async () => {
    const fetchMock = vi.spyOn(global, "fetch");
    render(<CustomerRegistration />);
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Asha Sharma" } });
    fireEvent.change(screen.getByLabelText("Age"), { target: { value: "34" } });
    fireEvent.change(screen.getByLabelText("Gender"), { target: { value: "FEMALE" } });
    fireEvent.change(screen.getByLabelText("Mobile number"), { target: { value: "9876543210" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "first-password" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "other-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Send OTP" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Passwords do not match.");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
