import { describe, expect, it, vi } from "vitest";

describe("MSG91 SDK loading", () => {
  it("reports a browser-blocked SDK accurately and removes the failed script for retry", async () => {
    vi.resetModules();
    document.head.innerHTML = '<script src="https://verify.msg91.com/otp-provider.js"></script>';
    delete (window as Window & { initSendOTP?: unknown }).initSendOTP;
    const append = vi.spyOn(document.head, "appendChild").mockImplementation((node) => {
      queueMicrotask(() => node.dispatchEvent(new Event("error")));
      return node;
    });
    const { sendMsg91Otp } = await import("@/lib/auth/msg91-widget");

    await expect(sendMsg91Otp(
      { enabled: true, widgetId: "widget-id", tokenAuth: "web-token" }, "9876543210",
    )).rejects.toThrow("Mobile verification could not be loaded.");
    expect(document.querySelectorAll('script[src="https://verify.msg91.com/otp-provider.js"]')).toHaveLength(0);
    expect(append).toHaveBeenCalledOnce();
  });
});
