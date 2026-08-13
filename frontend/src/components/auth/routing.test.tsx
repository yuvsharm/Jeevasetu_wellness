import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { StrictMode, type ReactNode } from "react";
import { beforeEach, vi } from "vitest";

import { DashboardRedirect } from "./dashboard-redirect";
import { ApplicantPage } from "./applicant-page";
import { ProtectedPage } from "./protected-page";
import { SessionProvider } from "./session-provider";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, refresh: vi.fn() }), usePathname: () => "/owner" }));

function wrapper(children: ReactNode) {
  return <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><SessionProvider>{children}</SessionProvider></QueryClientProvider>;
}

function session(role: "OWNER" | "MANAGER" | "PHYSIOTHERAPIST" | "CUSTOMER") {
  return { user: { id: "u", first_name: "A", last_name: "User", email: "", mobile_number: null, profile_image: "", roles: [role] }, access: { user_id: "u", organization: { id: "o", slug: "jeevasetu" }, permitted_clinics: [], roles: [{ id: "r", user_id: "u", organization_id: "o", clinic_id: null, role, scope: "organization", is_active: true }] } };
}

function applicantSession() {
  return { user: { id: "u", first_name: "A", last_name: "Applicant", email: "", mobile_number: null, profile_image: "", roles: [] }, access: { user_id: "u", organization: { id: "o", slug: "jeevasetu" }, permitted_clinics: [], roles: [] } };
}

describe("protected routing", () => {
  beforeEach(() => { replace.mockReset(); vi.restoreAllMocks(); });

  it.each([
    ["OWNER", "/owner"],
    ["MANAGER", "/manager"],
    ["PHYSIOTHERAPIST", "/physiotherapist"],
    ["CUSTOMER", "/customer"],
  ] as const)("redirects backend-confirmed %s access", async (role, destination) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(session(role)), { status: 200 }));
    render(wrapper(<DashboardRedirect />));
    await waitFor(() => expect(replace).toHaveBeenCalledWith(destination));
  });

  it("redirects an expired unauthenticated session to login", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "expired" }), { status: 401 }));
    render(wrapper(<DashboardRedirect />));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?reason=expired"));
  });

  it("refreshes stale applicant access before deciding an approved practitioner route", async () => {
    const responses = [applicantSession(), session("PHYSIOTHERAPIST")];
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response(JSON.stringify(responses.shift() ?? session("PHYSIOTHERAPIST")), { status: 200 }));
    render(wrapper(<ProtectedPage role="PHYSIOTHERAPIST" title="Practitioner"><p>Operational dashboard</p></ProtectedPage>));
    await waitFor(() => expect(document.body).toHaveTextContent("Operational dashboard"));
    expect(replace).not.toHaveBeenCalledWith("/unauthorized");
  });
  it("opens the Owner route after confirming OWNER access in development Strict Mode", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response(JSON.stringify(session("OWNER")), { status: 200 }));
    render(<StrictMode>{wrapper(<ProtectedPage role="OWNER" title="Owner"><p>Owner operations</p></ProtectedPage>)}</StrictMode>);
    await waitFor(() => expect(document.body).toHaveTextContent("Owner operations"));
    expect(replace).not.toHaveBeenCalledWith("/unauthorized");
  });
  it("denies a wrong-role route", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(session("CUSTOMER")), { status: 200 }));
    render(wrapper(<ProtectedPage role="OWNER" title="Owner"><p>Secret owner shell</p></ProtectedPage>));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/unauthorized"));
  });

  it("redirects a roleless applicant from dashboard to their application", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(applicantSession()), { status: 200 }));
    render(wrapper(<DashboardRedirect />));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/practitioner-application"));
  });

  it("allows an authenticated applicant without an operational role into only the application shell", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(applicantSession()), { status: 200 }));
    render(wrapper(<ApplicantPage><p>My practitioner application</p></ApplicantPage>));
    await waitFor(() => expect(document.body).toHaveTextContent("My practitioner application"));
    expect(replace).not.toHaveBeenCalled();
  });

  it("returns a truly expired applicant session to login with the application return URL", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "expired" }), { status: 401 }));
    render(wrapper(<ApplicantPage><p>Application</p></ApplicantPage>));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?reason=expired&returnTo=%2Fpractitioner-application"));
  });

  it("denies an applicant without an operational role from protected dashboards", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(applicantSession()), { status: 200 }));
    render(wrapper(<ProtectedPage role="OWNER" title="Owner"><p>Secret owner shell</p></ProtectedPage>));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/unauthorized"));
  });
});
