import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

function routeRequest(body: unknown, origin = "http://localhost") {
  return new NextRequest("http://localhost/api/location/reverse-geocode", {
    method: "POST",
    headers: { origin, host: "localhost", "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("reverse geocoding route", () => {
  afterEach(() => {
    delete process.env.GEOCODING_PROVIDER;
    delete process.env.GOOGLE_MAPS_GEOCODING_API_KEY;
    vi.restoreAllMocks();
  });

  it("returns JSON when no approved provider is configured", async () => {
    const response = await POST(routeRequest({ latitude: 28.61, longitude: 77.21 }));
    expect(response.status).toBe(503);
    expect(response.headers.get("content-type")).toContain("application/json");
    expect(response.headers.get("cache-control")).toBe("private, no-store");
    expect(await response.json()).toEqual({
      detail: "Reverse geocoding is not configured.",
      code: "NOT_CONFIGURED",
    });
  });

  it("rejects cross-origin use before contacting a provider", async () => {
    const provider = vi.spyOn(global, "fetch");
    const response = await POST(
      routeRequest({ latitude: 28.61, longitude: 77.21 }, "https://evil.example"),
    );
    expect(response.status).toBe(403);
    expect(provider).not.toHaveBeenCalled();
    expect(await response.json()).toEqual({ detail: "This request is not permitted." });
  });

  it("maps a configured Google result without exposing the server key", async () => {
    process.env.GEOCODING_PROVIDER = "google";
    process.env.GOOGLE_MAPS_GEOCODING_API_KEY = "server-secret";
    const provider = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        status: "OK",
        results: [{
          formatted_address: "163 C Block, Meerut",
          address_components: [
            { long_name: "163", types: ["premise"] },
            { long_name: "C Block", types: ["route"] },
            { long_name: "Meerut", types: ["locality"] },
            { long_name: "Uttar Pradesh", types: ["administrative_area_level_1"] },
            { long_name: "250004", types: ["postal_code"] },
          ],
        }],
      }), { status: 200 }),
    );
    const response = await POST(routeRequest({ latitude: 28.61, longitude: 77.21 }));
    const responseText = await response.text();
    expect(response.status).toBe(200);
    expect(JSON.parse(responseText)).toMatchObject({
      address_line_1: "163 C Block",
      city: "Meerut",
      region: "Uttar Pradesh",
      pin_code: "250004",
    });
    expect(String(provider.mock.calls[0][0])).toContain("key=server-secret");
    expect(responseText).not.toContain("server-secret");
  });
});
