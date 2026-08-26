import { beforeEach, describe, expect, it, vi } from "vitest";

import { sendMsg91Otp, verifyMsg91Otp } from "@/lib/auth/msg91-widget";

describe("MSG91 OTP widget adapter", () => {
  beforeEach(() => {
    document.head.innerHTML = '<script src="https://verify.msg91.com/otp-provider.js"></script>';
  });

  it("sends an Indian mobile identifier and returns only the verified access token", async () => {
    const initSendOTP = vi.fn();
    const sendOtp = vi.fn((_mobile, success) => success({ type: "success" }));
    const verifyOtp = vi.fn((_otp, success) => success({ type: "success", message: { "access-token": "verified-token" } }));
    Object.assign(window, { initSendOTP, sendOtp, verifyOtp });
    const config = { enabled: true as const, widgetId: "widget-id", tokenAuth: "web-token" };

    await sendMsg91Otp(config, "9876543210");
    expect(initSendOTP).toHaveBeenCalledWith(expect.objectContaining({ widgetId: "widget-id", exposeMethods: true }));
    expect(sendOtp).toHaveBeenCalledWith("919876543210", expect.any(Function), expect.any(Function));
    await expect(verifyMsg91Otp(config, "654321")).resolves.toBe("verified-token");
  });

  it("fails closed when MSG91 does not return an access token", async () => {
    Object.assign(window, {
      initSendOTP: vi.fn(),
      verifyOtp: vi.fn((_otp, success) => success({ type: "success" })),
    });
    await expect(verifyMsg91Otp(
      { enabled: true, widgetId: "widget-id", tokenAuth: "web-token" }, "654321",
    )).rejects.toThrow(/valid access token/i);
  });
});
