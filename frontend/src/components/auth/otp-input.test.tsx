import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { maskMobile, OtpInput, OtpResendButton } from "./otp-input";

function Harness() { const [value, setValue] = useState(""); return <OtpInput value={value} onChange={setValue} mobileNumber="9876543210"/>; }

describe("OtpInput", () => {
  afterEach(() => vi.restoreAllMocks());
  it("supports numeric manual entry, complete-code paste and masks the mobile", () => {
    render(<Harness/>);
    const input = screen.getByLabelText("One-time password");
    expect(input).toHaveAttribute("autocomplete", "one-time-code");
    expect(input).toHaveAttribute("inputmode", "numeric");
    expect(screen.getByText(/••••••3210/)).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "12a34" } });
    expect(input).toHaveValue("1234");
    fireEvent.paste(input, { clipboardData: { getData: () => "98 76-54" } });
    expect(input).toHaveValue("987654");
    expect(maskMobile("+91 98765 43210")).toBe("••••••3210");
  });
  it("uses WebOTP only when feature-detected in a secure context", async () => {
    Object.defineProperty(window, "isSecureContext", { value: true, configurable: true });
    Object.defineProperty(window, "OTPCredential", { value: function OTPCredential(){}, configurable: true });
    const get = vi.fn().mockResolvedValue({ code: "123456" });
    Object.defineProperty(navigator, "credentials", { value: { get }, configurable: true });
    render(<Harness/>);
    expect(await screen.findByText("SMS code detected. Review it, then verify.")).toBeInTheDocument();
    expect(screen.getByLabelText("One-time password")).toHaveValue("123456");
    expect(get).toHaveBeenCalledTimes(1);
  });
  it("keeps resend disabled during the cooldown and prevents repeated clicks", async () => {
    vi.useFakeTimers();
    const resend = vi.fn();
    render(<OtpResendButton onResend={resend} cooldownSeconds={2}/>);
    expect(screen.getByRole("button", { name: "Resend code in 0:02" })).toBeDisabled();
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    fireEvent.click(screen.getByRole("button", { name: "Resend OTP" }));
    await act(async () => undefined);
    expect(resend).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Resend code in 0:02" })).toBeDisabled();
    vi.useRealTimers();
  });
});
