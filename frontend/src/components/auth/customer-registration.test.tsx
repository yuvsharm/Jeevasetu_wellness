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

function fillDetails() {
  fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Asha Sharma" } });
  fireEvent.change(screen.getByLabelText("Age"), { target: { value: "34" } });
  fireEvent.change(screen.getByLabelText("Gender"), { target: { value: "FEMALE" } });
  fireEvent.change(screen.getByLabelText("Mobile number"), { target: { value: "9876543210" } });
  fireEvent.change(screen.getByLabelText("Email (optional)"), { target: { value: "asha@example.com" } });
  fireEvent.change(screen.getByLabelText("Address"), { target: { value: "163 C Block" } });
  fireEvent.change(screen.getByLabelText("PIN code"), { target: { value: "250004" } });
}

function providerFetch() {
  return vi.spyOn(global, "fetch").mockImplementation(async (input) => {
    if (String(input) === "/api/booking-otp/issue") return new Response(JSON.stringify({ verification_id: "verification-1" }), { status: 201 });
    if (String(input) === "/api/booking-otp/verify") return new Response(JSON.stringify({ token: "server-signed-mobile-proof" }), { status: 200 });
    if (String(input) === "/api/session/customer-register") return new Response(JSON.stringify({ user: { id: "customer-1" } }), { status: 201 });
    return new Response(JSON.stringify({}), { status: 200 });
  });
}

async function reachSecureStep() {
  fillDetails();
  fireEvent.click(screen.getByRole("button", { name: "Send OTP" }));
  fireEvent.change(await screen.findByLabelText("One-time password"), { target: { value: "654321" } });
  fireEvent.click(screen.getByRole("button", { name: "Verify Mobile" }));
  await screen.findByText("Mobile number verified");
}

describe("customer registration", () => {
  beforeEach(() => { vi.restoreAllMocks(); replace.mockClear(); });

  it("hides passwords until server-backed OTP verification unlocks Step 2", async () => {
    const fetchMock = providerFetch();
    render(<CustomerRegistration />);
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Confirm password")).not.toBeInTheDocument();
    await reachSecureStep();
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
    expect(screen.getByLabelText("Confirm password")).toHaveAttribute("type", "password");
    const verifyCall = fetchMock.mock.calls.find(([input]) => String(input) === "/api/booking-otp/verify");
    expect(JSON.parse(String(verifyCall?.[1]?.body))).toMatchObject({ verification_id: "verification-1", mobile_number: "9876543210", access_token: "header.payload.signature" });
  });

  it("creates the customer with signed proof and sends them to customer login", async () => {
    const fetchMock = providerFetch();
    render(<CustomerRegistration />);
    await reachSecureStep();
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "Asha-Strong-Password-2026!" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "Asha-Strong-Password-2026!" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Account" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/customer-login?registered=1&returnTo=%2Fbook-appointment%3Ftherapy%3Dtherapy-1"));
    expect(replace).not.toHaveBeenCalledWith(expect.stringMatching(/^\/login/));
    const call = fetchMock.mock.calls.find(([input]) => String(input) === "/api/session/customer-register");
    const submitted = call?.[1]?.body as FormData;
    const body = JSON.parse(String(submitted.get("payload")));
    expect(body).toMatchObject({ booking_verification_token: "server-signed-mobile-proof", mobile_number: "9876543210", email: "asha@example.com", password: "Asha-Strong-Password-2026!", confirm_password: "Asha-Strong-Password-2026!" });
    expect(body).not.toHaveProperty("otp");
    expect(body).not.toHaveProperty("access_token");
    expect(body).not.toHaveProperty("authkey");
    expect(submitted.get("profile_photo")).toBeNull();
  });

  it("allows an optional photo to be selected, replaced or removed before submission", async () => {
    const fetchMock = providerFetch();
    render(<CustomerRegistration />);
    const first = new File(["one"], "first.png", { type: "image/png" });
    const replacement = new File(["two"], "second.webp", { type: "image/webp" });
    fireEvent.change(screen.getByLabelText("Profile photo"), { target: { files: [first] } });
    expect(screen.getByRole("button", { name: "Remove selected photo" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Profile photo"), { target: { files: [replacement] } });
    await reachSecureStep();
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "Asha-Strong-Password-2026!" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "Asha-Strong-Password-2026!" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Account" }));
    await waitFor(() => expect(replace).toHaveBeenCalled());
    const call = fetchMock.mock.calls.find(([input]) => String(input) === "/api/session/customer-register");
    expect((call?.[1]?.body as FormData).get("profile_photo")).toBe(replacement);
  });

  it("provides independent password controls and blocks mismatched passwords", async () => {
    const fetchMock = providerFetch();
    render(<CustomerRegistration />);
    await reachSecureStep();
    const password = screen.getByLabelText("Password");
    const confirmation = screen.getByLabelText("Confirm password");
    fireEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    expect(confirmation).toHaveAttribute("type", "password");
    fireEvent.change(password, { target: { value: "Strong1!" } });
    fireEvent.change(confirmation, { target: { value: "Other2!x" } });
    expect(screen.getByText("✕ Passwords do not match")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create Account" })).toBeDisabled();
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/session/customer-register")).toBe(false);
  });

  it("invalidates verified state before the mobile can be changed", async () => {
    providerFetch();
    render(<CustomerRegistration />);
    await reachSecureStep();
    fireEvent.click(screen.getByRole("button", { name: "Back to Step 1" }));
    fireEvent.change(screen.getByLabelText("Mobile number"), { target: { value: "9876543211" } });
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
    expect(screen.queryByText("Mobile number verified")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send OTP" })).toBeInTheDocument();
  });

  it("displays registration retry timing returned by the session API", async () => {
    vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      if (String(input) === "/api/booking-otp/issue") return new Response(JSON.stringify({ verification_id: "verification-1" }), { status: 201 });
      if (String(input) === "/api/booking-otp/verify") return new Response(JSON.stringify({ token: "server-signed-mobile-proof" }), { status: 200 });
      return new Response(JSON.stringify({ detail: "Too many registration attempts. Please try again in 10 minutes.", retry_after: 600 }), { status: 429 });
    });
    render(<CustomerRegistration />);
    await reachSecureStep();
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "Asha-Strong-Password-2026!" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "Asha-Strong-Password-2026!" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many registration attempts. Please try again in 10 minutes.");
  });

  it("shows the actionable backend registration error instead of a generic field-zero message", async () => {
    vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      if (String(input) === "/api/booking-otp/issue") return new Response(JSON.stringify({ verification_id: "verification-1" }), { status: 201 });
      if (String(input) === "/api/booking-otp/verify") return new Response(JSON.stringify({ token: "server-signed-mobile-proof" }), { status: 200 });
      return new Response(JSON.stringify({
        detail: "This mobile number is already registered. Please sign in.",
        fieldErrors: { mobile_number: "This mobile number is already registered. Please sign in." },
      }), { status: 400 });
    });
    render(<CustomerRegistration />);
    await reachSecureStep();
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "Asha-Strong-Password-2026!" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "Asha-Strong-Password-2026!" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This mobile number is already registered. Please sign in.");
    expect(screen.queryByText("Please review the highlighted information.")).not.toBeInTheDocument();
  });
});
