import type { ReverseGeocodeResult } from "./contracts";

type GoogleComponent = { long_name: string; types: string[] };
type GoogleResult = { formatted_address: string; address_components: GoogleComponent[] };

export class ReverseGeocodeError extends Error {
  constructor(public readonly code: "NOT_CONFIGURED" | "UNSUPPORTED_PROVIDER" | "RATE_LIMITED" | "NO_RESULT" | "PROVIDER_UNAVAILABLE") {
    super(code);
  }
}

const component = (values: GoogleComponent[], type: string) =>
  values.find((value) => value.types.includes(type))?.long_name ?? "";

export async function reverseGeocode(latitude: number, longitude: number): Promise<ReverseGeocodeResult> {
  const provider = process.env.GEOCODING_PROVIDER?.trim().toLowerCase();
  if (!provider) throw new ReverseGeocodeError("NOT_CONFIGURED");
  if (provider !== "google") throw new ReverseGeocodeError("UNSUPPORTED_PROVIDER");
  const key = process.env.GOOGLE_MAPS_GEOCODING_API_KEY;
  if (!key || key === "your-restricted-server-geocoding-key") throw new ReverseGeocodeError("NOT_CONFIGURED");

  const url = new URL("https://maps.googleapis.com/maps/api/geocode/json");
  url.searchParams.set("latlng", `${latitude},${longitude}`);
  url.searchParams.set("key", key);
  const response = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(8_000) });
  if (response.status === 429) throw new ReverseGeocodeError("RATE_LIMITED");
  if (!response.ok) throw new ReverseGeocodeError("PROVIDER_UNAVAILABLE");
  let body: { status: string; results?: GoogleResult[] };
  try { body = await response.json() as typeof body; }
  catch { throw new ReverseGeocodeError("PROVIDER_UNAVAILABLE"); }
  const first = body.results?.[0];
  if (body.status === "OVER_QUERY_LIMIT") throw new ReverseGeocodeError("RATE_LIMITED");
  if (body.status !== "OK" || !first) throw new ReverseGeocodeError("NO_RESULT");
  const parts = first.address_components;
  const streetNumber = component(parts, "street_number");
  const route = component(parts, "route");
  const premise = component(parts, "premise") || component(parts, "subpremise");
  return {
    address_line_1: [premise, streetNumber, route].filter(Boolean).join(" "),
    address_line_2: component(parts, "sublocality_level_1") || component(parts, "neighborhood"),
    landmark: "",
    city: component(parts, "locality") || component(parts, "administrative_area_level_2"),
    region: component(parts, "administrative_area_level_1"),
    pin_code: component(parts, "postal_code"),
    display_address: first.formatted_address,
    provider: "google",
  };
}
