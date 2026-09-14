import { NextRequest, NextResponse } from "next/server";
import { reverseGeocode, ReverseGeocodeError } from "@/lib/location/reverse-geocoder";

const safeErrors = {
  NOT_CONFIGURED: "Reverse geocoding is not configured.",
  UNSUPPORTED_PROVIDER: "The configured reverse-geocoding provider is unsupported.",
  RATE_LIMITED: "Address lookup is temporarily busy. Please retry shortly.",
  NO_RESULT: "No complete postal address was found for this location.",
  PROVIDER_UNAVAILABLE: "The address provider is temporarily unavailable.",
} as const;

function json(body: unknown, status = 200) {
  return NextResponse.json(body, { status, headers: { "Cache-Control": "private, no-store" } });
}

function isSameOrigin(request: NextRequest) {
  const origin = request.headers.get("origin");
  if (!origin) return true;
  const protocol = request.headers.get("x-forwarded-proto") ?? request.nextUrl.protocol.slice(0, -1);
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  return Boolean(host && origin === `${protocol}://${host}`);
}

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) return json({ detail: "This request is not permitted." }, 403);
  let body: { latitude?: number; longitude?: number };
  try { body = await request.json(); }
  catch { return json({ detail: "Location coordinates are invalid." }, 400); }
  const latitude = Number(body.latitude), longitude = Number(body.longitude);
  if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90 ||
      !Number.isFinite(longitude) || longitude < -180 || longitude > 180) {
    return json({ detail: "Location coordinates are invalid." }, 400);
  }
  try { return json(await reverseGeocode(latitude, longitude)); }
  catch (error) {
    const code = error instanceof ReverseGeocodeError ? error.code : "PROVIDER_UNAVAILABLE";
    return json(
      { detail: safeErrors[code], code },
      code === "RATE_LIMITED" ? 429 : 503,
    );
  }
}
