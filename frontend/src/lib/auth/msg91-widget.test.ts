import { beforeEach, describe, expect, it, vi } from "vitest";

import { sendMsg91Otp, verifyMsg91Otp } from "@/lib/auth/msg91-widget";

const jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ2ZXJpZmllZCJ9.signature";

describe("MSG91 OTP widget adapter", () => {
  beforeEach(() => {
    vi.useRealTimers();
    document.head.innerHTML = '<script src="https://verify.msg91.com/otp-provider.js"></script>';
    delete (window as Window & { initSendOTP?: unknown }).initSendOTP;
    delete (window as Window & { sendOtp?: unknown }).sendOtp;
    delete (window as Window & { verifyOtp?: unknown }).verifyOtp;
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
      initializationSuccess?.(jwt);
    });
    Object.assign(window, { initSendOTP, sendOtp: vi.fn(), verifyOtp });
    const config = { enabled: true as const, widgetId: "widget-id", tokenAuth: "web-token" };

    await expect(verifyMsg91Otp(config, "654321")).resolves.toBe(jwt);
    expect(verifyOtp).toHaveBeenCalledWith("654321", expect.any(Function), expect.any(Function));
  });

  it("waits for MSG91 to expose custom-UI methods after initSendOTP returns", async () => {
    const sendOtp = vi.fn((_mobile, success) => success({ type: "success" }));
    const verifyOtp = vi.fn((_otp, success) => success({ type: "success", message: jwt }));
    const initSendOTP = vi.fn(() => {
      setTimeout(() => Object.assign(window, { sendOtp, verifyOtp }), 1);
    });
    Object.assign(window, { initSendOTP });
    const config = { enabled: true as const, widgetId: "widget-id", tokenAuth: "web-token" };

    await sendMsg91Otp(config, "9876543210");
    expect(sendOtp).toHaveBeenCalledOnce();
    await expect(verifyMsg91Otp(config, "654321")).resolves.toBe(jwt);
  });

  it("captures the runtime MSG91 response shape with a JWT in message", async () => {
    Object.assign(window, {
      initSendOTP: vi.fn(),
      sendOtp: vi.fn(),
      verifyOtp: vi.fn((_otp, success) => success({ type: "success", message: jwt })),
    });
    await expect(verifyMsg91Otp(
      { enabled: true, widgetId: "widget-id", tokenAuth: "web-token" }, "654321",
    )).resolves.toBe(jwt);
  });

  it("waits for the initialization callback when the method callback has no token", async () => {
    let initializationSuccess: ((data: unknown) => void) | undefined;
    Object.assign(window, {
      initSendOTP: vi.fn((configuration: Record<string, unknown>) => {
        initializationSuccess = configuration.success as (data: unknown) => void;
      }),
      sendOtp: vi.fn(),
      verifyOtp: vi.fn((_otp, success) => {
        success({ type: "success", message: "OTP verified" });
        setTimeout(() => initializationSuccess?.({ type: "success", message: jwt }), 0);
      }),
    });
    await expect(verifyMsg91Otp(
      { enabled: true, widgetId: "widget-id", tokenAuth: "web-token" }, "654321",
    )).resolves.toBe(jwt);
  });

  it("fails closed when MSG91 does not return an access token", async () => {
    vi.useFakeTimers();
    Object.assign(window, {
      initSendOTP: vi.fn(),
      sendOtp: vi.fn(),
      verifyOtp: vi.fn((_otp, success) => success({ type: "success" })),
    });
    const verification = verifyMsg91Otp(
      { enabled: true, widgetId: "widget-id", tokenAuth: "web-token" }, "654321",
    );
    const expectation = expect(verification).rejects.toThrow(/valid access token/i);
    await vi.advanceTimersByTimeAsync(5000);
    await expectation;
    vi.useRealTimers();
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
