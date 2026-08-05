import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, vi } from "vitest";

import { ForgotPasswordForm, LoginForm, RegistrationForm } from "./auth-forms";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

describe("authentication forms", () => {
  beforeEach(() => {
    replace.mockReset();
    vi.restoreAllMocks();
  });

  it("provides accessible login labels and client validation", async () => {
    render(<LoginForm />);
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
    render(<LoginForm />);
    await userEvent.type(screen.getByLabelText(/email or mobile/i), "owner@example.com");
    await userEvent.type(screen.getByLabelText(/^password$/i), "StrongPassword42");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(screen.getByRole("button", { name: /signing in/i })).toBeDisabled();
    resolveRequest?.(new Response(JSON.stringify({ user: {}, access: {} }), { status: 200 }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
  });

  it("shows a safe invalid-credential message", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "The credentials or session are invalid." }), { status: 401 }),
    );
    render(<LoginForm />);
    await userEvent.type(screen.getByLabelText(/email or mobile/i), "owner@example.com");
    await userEvent.type(screen.getByLabelText(/^password$/i), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/credentials or session are invalid/i);
  });

  it("validates registration consent and password confirmation", async () => {
    render(<RegistrationForm />);
    await userEvent.click(screen.getByRole("button", { name: /create account/i }));
    expect(await screen.findByText(/accept the terms and privacy/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/first name/i)).toBeRequired();
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
