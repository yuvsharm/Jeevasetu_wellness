// @vitest-environment node
import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { POST } from "./appointment-requests/route";
import { GET } from "./appointment-therapies/route";
import { POST as issueOtp } from "./booking-otp/issue/route";
import { POST as verifyOtp } from "./booking-otp/verify/route";
import { POST as createQuickAppointment } from "./quick-appointment-requests/route";

describe("public appointment gateways", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("lists live therapies without session cookies", async () => {
    const backend = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify([{ id: "therapy-1", name: "Physiotherapy" }]), { status: 200, headers: { "Content-Type": "application/json" } }));
    const response = await GET(new NextRequest("http://localhost:3000/api/appointment-therapies"));
    expect(response.status).toBe(200);
    expect((backend.mock.calls[0]?.[1]?.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it("passes anonymous requests to the existing public Django endpoint", async () => {
    const backend = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ id: "request-1", status: "PENDING" }), { status: 201, headers: { "Content-Type": "application/json" } }));
    const request = new NextRequest("http://localhost:3000/api/appointment-requests", { method: "POST", body: JSON.stringify({ patient_name: "Guest" }), headers: { "Content-Type": "application/json" } });
    const response = await POST(request);
    expect(response.status).toBe(201);
    expect((backend.mock.calls[0]?.[1]?.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it.each([
    [issueOtp, "/api/booking-otp/issue", "/appointments/booking-otp/issue/"],
    [verifyOtp, "/api/booking-otp/verify", "/appointments/booking-otp/verify/"],
    [createQuickAppointment, "/api/quick-appointment-requests", "/appointments/quick-requests/"],
  ])("proxies the secure public flow without requiring session cookies", async (handler, frontendPath, backendPath) => {
    const backend = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }));
    const request = new NextRequest(`http://localhost:3000${frontendPath}`, { method: "POST", body: "{}", headers: { "Content-Type": "application/json" } });
    const response = await handler(request);
    expect(response.status).toBe(200);
    expect(backend.mock.calls[0]?.[0]).toBe(`http://localhost:8000/api/v1${backendPath}`);
    expect((backend.mock.calls[0]?.[1]?.headers as Record<string, string>).Authorization).toBeUndefined();
  });
});
