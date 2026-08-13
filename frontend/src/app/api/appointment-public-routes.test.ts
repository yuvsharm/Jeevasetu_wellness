// @vitest-environment node
import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { POST } from "./appointment-requests/route";
import { GET } from "./appointment-therapies/route";

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
});
