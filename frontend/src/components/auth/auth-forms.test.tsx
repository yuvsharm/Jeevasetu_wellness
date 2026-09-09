import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ForgotPasswordForm, LoginForm, RegistrationForm } from "./auth-forms";
import { DashboardRedirect } from "./dashboard-redirect";
import { SessionProvider } from "./session-provider";
import { ClientApiError } from "@/lib/api/client";

const ownerSession = {
  user: { id: "owner", first_name: "Session", last_name: "Owner", email: "", mobile_number: null, profile_image: "", roles: ["OWNER"] },
  access: { user_id: "owner", organization: { id: "org", slug: "jeevasetu-wellness" }, permitted_clinics: [], roles: [{ id: "role", user_id: "owner", organization_id: "org", clinic_id: null, role: "OWNER", scope: "organization", is_active: true }] },
};

const replace = vi.fn();
let query = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh: vi.fn() }),
  useSearchParams: () => query,
}));

describe("authentication forms", () => {
  beforeEach(() => {
    replace.mockReset();
    query = new URLSearchParams();
    vi.restoreAllMocks();
  });

  it("returns an applicant to onboarding after sign in", async () => {
    query = new URLSearchParams("returnTo=/practitioner-application");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ user: {}, access: { roles: [] } }), { status: 200 }));
    render(<QueryClientProvider client={new QueryClient()}><LoginForm /></QueryClientProvider>);
    await userEvent.type(screen.getByLabelText(/email or mobile/i), "applicant@example.com");
    await userEvent.type(screen.getByLabelText(/^password$/i), "StrongPassword42");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/practitioner-application"));
  });

  it("provides accessible login labels and client validation", async () => {
    render(<QueryClientProvider client={new QueryClient()}><LoginForm /></QueryClientProvider>);
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText(/enter your email or mobile number/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toHaveAttribute("type", "password");
    await userEvent.click(screen.getByRole("button", { name: /show password/i }));
    expect(screen.getByLabelText(/password/i)).toHaveAttribute("type", "text");
  });

  it("shows loading and redirects after successful login", async () => {
    let resolveRequest: ((response: Response) => void) | undefined;
    vi.spyOn(globalThis, "fetch").mockReturnValue(
      new Promise((resolve) => { resolveRequest = resolve; }),
    );
    const client = new QueryClient();
    await client.fetchQuery({ queryKey: ["session"], queryFn: async () => { throw new Error("pre-login 401"); }, retry: false }).catch(() => undefined);
    expect(client.getQueryState(["session"])?.status).toBe("error");
    render(<QueryClientProvider client={client}><LoginForm /></QueryClientProvider>);
    await userEvent.type(screen.getByLabelText(/email or mobile/i), "owner@example.com");
    await userEvent.type(screen.getByLabelText(/^password$/i), "StrongPassword42");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(screen.getByRole("button", { name: /signing in/i })).toBeDisabled();
    resolveRequest?.(new Response(JSON.stringify({ user: {}, access: {} }), { status: 200 }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
    expect(client.getQueryData(["session"])).toEqual({ user: {}, access: {} });
    expect(client.getQueryState(["session"])?.status).toBe("success");
  });

  it("does not let an in-flight pre-login 401 overwrite a successful login", async () => {
    let rejectStale: ((reason: unknown) => void) | undefined;
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const staleRequest = client.fetchQuery({
      queryKey: ["session"],
      queryFn: () => new Promise((_, reject) => { rejectStale = reject; }),
    }).catch(() => undefined);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(ownerSession), { status: 200 }));
    const loginView = render(<QueryClientProvider client={client}><LoginForm /></QueryClientProvider>);
    await userEvent.type(screen.getByLabelText(/email or mobile/i), "owner@example.com");
    await userEvent.type(screen.getByLabelText(/^password$/i), "StrongPassword42");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
    rejectStale?.(new ClientApiError(401, undefined, "expired"));
    await staleRequest;
    expect(client.getQueryData(["session"])).toEqual(ownerSession);
    expect(client.getQueryState(["session"])?.status).toBe("success");
    loginView.unmount();
    render(<QueryClientProvider client={client}><SessionProvider><DashboardRedirect /></SessionProvider></QueryClientProvider>);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/owner"));
    expect(replace).not.toHaveBeenCalledWith("/login?reason=expired");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("cancels a loading pre-login session request before seeding authenticated state", async () => {
    let aborted = false;
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    void client.fetchQuery({
      queryKey: ["session"],
      queryFn: ({ signal }) => new Promise((_, reject) => signal.addEventListener("abort", () => { aborted = true; reject(new DOMException("Aborted", "AbortError")); })),
    }).catch(() => undefined);
    expect(client.getQueryState(["session"])?.fetchStatus).toBe("fetching");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(ownerSession), { status: 200 }));
    render(<QueryClientProvider client={client}><LoginForm /></QueryClientProvider>);
    await userEvent.type(screen.getByLabelText(/email or mobile/i), "owner@example.com");
    await userEvent.type(screen.getByLabelText(/^password$/i), "StrongPassword42");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
    expect(aborted).toBe(true);
    expect(client.getQueryData(["session"])).toEqual(ownerSession);
    expect(client.getQueryState(["session"])?.status).toBe("success");
  });

  it("shows a safe invalid-credential message", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "The credentials or session are invalid." }), { status: 401 }),
    );
    render(<QueryClientProvider client={new QueryClient()}><LoginForm /></QueryClientProvider>);
    await userEvent.type(screen.getByLabelText(/email or mobile/i), "owner@example.com");
    await userEvent.type(screen.getByLabelText(/^password$/i), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/credentials or session are invalid/i);
  });

  it("validates registration consent and password confirmation", async () => {
    render(<RegistrationForm />);
    await userEvent.type(screen.getByLabelText(/^password$/i), "Strong1!");
    await userEvent.type(screen.getByLabelText(/confirm password/i), "Strong1!");
    await userEvent.click(screen.getByRole("button", { name: /create account/i }));
    expect(await screen.findByText(/accept the terms and privacy/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/first name/i)).toBeRequired();
  });

  it("shows live password rules and blocks clipboard use in confirmation", () => {
    render(<RegistrationForm />);
    const password = screen.getByLabelText(/^password$/i);
    const confirmation = screen.getByLabelText(/confirm password/i);
    expect(fireEvent.paste(password)).toBe(true);
    expect(fireEvent.paste(confirmation)).toBe(false);
    expect(screen.getByText(/please type the password again manually/i)).toBeInTheDocument();
    expect(screen.getByText(/one special character/i)).toBeInTheDocument();
  });

  it("always renders the generic password-reset response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "accepted" }), { status: 202 }),
    );
    render(<ForgotPasswordForm />);
    await userEvent.type(screen.getByLabelText(/email or mobile/i), "unknown@example.com");
    await userEvent.click(screen.getByRole("button", { name: /request reset/i }));
    expect(await screen.findByText(/if an eligible account exists/i)).toBeInTheDocument();
  });
});
