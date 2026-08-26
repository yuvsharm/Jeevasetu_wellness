import { afterEach, describe, expect, it } from "vitest";

import { GET } from "./route";

const original = { ...process.env };

describe("OTP widget configuration route", () => {
  afterEach(() => { process.env = { ...original }; });

  it("exposes only the browser widget configuration", async () => {
    process.env.MSG91_ENABLED = "true";
    process.env.MSG91_WIDGET_ID = "widget-id";
    process.env.MSG91_WIDGET_TOKEN = "web-token";
    process.env.MSG91_AUTH_KEY = "must-remain-server-only";
    const response = await GET();
    const body = await response.json();
    expect(body).toEqual({ enabled: true, widgetId: "widget-id", tokenAuth: "web-token" });
    expect(JSON.stringify(body)).not.toContain("must-remain-server-only");
  });

  it("does not expose placeholder configuration when disabled", async () => {
    process.env.MSG91_ENABLED = "false";
    expect(await (await GET()).json()).toEqual({ enabled: false });
  });
});
