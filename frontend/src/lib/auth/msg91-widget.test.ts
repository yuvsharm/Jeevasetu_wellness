import { beforeEach, describe, expect, it, vi } from "vitest";

import { sendMsg91Otp, verifyMsg91Otp } from "@/lib/auth/msg91-widget";

describe("MSG91 OTP widget adapter", () => {
  beforeEach(() => {
    document.head.innerHTML = '<script src="https://verify.msg91.com/otp-provider.js"></script>';
    vi.restoreAllMocks();
  });

  it("supplies required initialization callbacks and captures the verified access token", async () => {
    const initSendOTP = vi.fn();
    const sendOtp = vi.fn((_mobile, success) => success({ type: "success" }));
    const verifyOtp = vi.fn((_otp, success) => success({ type: "success", message: { "access-token": "verified-token" } }));
    Object.assign(window, { initSendOTP, sendOtp, verifyOtp });
    const config = { enabled: true as const, widgetId: "widget-id", tokenAuth: "web-token" };

    await sendMsg91Otp(config, "9876543210");
    expect(initSendOTP).toHaveBeenCalledWith(expect.objectContaining({
      widgetId: "widget-id",
      exposeMethods: true,
      success: expect.any(Function),
      failure: expect.any(Function),
    }));
    expect(sendOtp).toHaveBeenCalledWith("919876543210", expect.any(Function), expect.any(Function));
    await expect(verifyMsg91Otp(config, "654321")).resolves.toBe("verified-token");
  });

  it("captures a token delivered through the initialization success callback", async () => {
    let initializationSuccess: ((data: unknown) => void) | undefined;
    const initSendOTP = vi.fn((configuration: Record<string, unknown>) => {
      initializationSuccess = configuration.success as (data: unknown) => void;
    });
    const verifyOtp = vi.fn(() => {
      initializationSuccess?.({ type: "success", message: "verified", "access-token": "callback-token" });
    });
    Object.assign(window, { initSendOTP, verifyOtp });
    const config = { enabled: true as const, widgetId: "widget-id", tokenAuth: "web-token" };

    await expect(verifyMsg91Otp(config, "654321")).resolves.toBe("callback-token");
    expect(verifyOtp).toHaveBeenCalledWith("654321", expect.any(Function), expect.any(Function));
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

  it("turns initialization errors into a user-friendly failure without logging secrets", async () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    Object.assign(window, { initSendOTP: vi.fn(() => { throw new Error("web-token secret detail"); }) });

    await expect(sendMsg91Otp(
      { enabled: true, widgetId: "widget-id", tokenAuth: "web-token" }, "9876543210",
    )).rejects.toThrow("Mobile verification could not be initialized.");
    expect(error).not.toHaveBeenCalled();
    expect(log).not.toHaveBeenCalled();
  });
});
