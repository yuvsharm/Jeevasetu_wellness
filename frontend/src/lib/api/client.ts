import type { SafeApiError } from "@/lib/api/contracts";

export class ClientApiError extends Error {
  constructor(
    public status: number,
    public fieldErrors?: Record<string, string>,
    detail = "Something went wrong. Please try again.",
  ) {
    super(detail);
  }
}

export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ClientApiError(503, undefined, "The service is unavailable. Check your connection and retry.");
  }
  if (!response.ok) {
    let error: SafeApiError = { detail: "Something went wrong. Please try again." };
    try {
      const payload: unknown = await response.json();
      if (Array.isArray(payload)) {
        const messages = payload.filter((value): value is string => typeof value === "string");
        if (messages.length) error = { detail: messages.join(" ") };
      } else if (payload && typeof payload === "object") {
        const values = payload as Record<string, unknown>;
        const detail = Array.isArray(values.detail)
          ? values.detail.filter((value): value is string => typeof value === "string").join(" ")
          : typeof values.detail === "string" ? values.detail : error.detail;
        const fieldErrors = Object.fromEntries(Object.entries(values)
          .filter(([field]) => field !== "detail")
          .map(([field, value]) => [field, Array.isArray(value) ? value.join(" ") : String(value)]));
        error = { detail, ...(Object.keys(fieldErrors).length ? { fieldErrors } : {}) };
      }
    } catch {
      // The safe fallback above intentionally hides unexpected response details.
    }
    throw new ClientApiError(response.status, error.fieldErrors, error.detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
