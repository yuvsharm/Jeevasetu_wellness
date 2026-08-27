import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CustomerPasswordLogin } from "./customer-password-login";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, refresh: vi.fn() }), useSearchParams: () => new URLSearchParams("returnTo=%2Fbook-appointment") }));

describe("customer password login", () => {
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
