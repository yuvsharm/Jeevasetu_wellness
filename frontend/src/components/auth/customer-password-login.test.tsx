import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CustomerPasswordLogin } from "./customer-password-login";

const replace = vi.fn();
let searchParams = "returnTo=%2Fbook-appointment";
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, refresh: vi.fn() }), useSearchParams: () => new URLSearchParams(searchParams) }));

describe("customer password login", () => {
  beforeEach(() => { searchParams = "returnTo=%2Fbook-appointment"; replace.mockReset(); vi.restoreAllMocks(); });

  it("shows the post-registration confirmation on the customer login page", () => {
    searchParams = "registered=1&returnTo=%2Fcustomer";
    render(<CustomerPasswordLogin />);
    expect(screen.getByRole("status")).toHaveTextContent("Account created successfully. Please sign in.");
  });

  it("shows an expired customer-session message without using staff login", () => {
    searchParams = "reason=expired";
    render(<CustomerPasswordLogin />);
    expect(screen.getByRole("status")).toHaveTextContent("Your customer session has expired");
  });

  it("submits mobile and password without issuing OTP", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({}), { status: 200 }));
    render(<CustomerPasswordLogin />);
    fireEvent.change(screen.getByLabelText("Mobile number"), { target: { value: "9876543210" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "customer-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Open customer dashboard" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/book-appointment"));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/session/customer-login", expect.objectContaining({ body: JSON.stringify({ mobile_number: "9876543210", password: "customer-password" }) }));
  });

  it("provides an accessible password toggle and customer reset link", () => {
    render(<CustomerPasswordLogin />);
    expect(screen.getByRole("link", { name: "Forgot password?" })).toHaveAttribute("href", "/customer-forgot-password?returnTo=%2Fbook-appointment");
    const password = screen.getByLabelText("Password");
    expect(password).toHaveAttribute("type", "password");
    fireEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
  });
});
