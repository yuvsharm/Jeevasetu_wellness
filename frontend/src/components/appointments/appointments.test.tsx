import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BookingForm } from "@/components/appointments/booking-form";
import { CustomerRequests } from "@/components/appointments/customer-requests";
import { OwnerRequests } from "@/components/appointments/owner-requests";

function renderWithQuery(ui: React.ReactNode) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>{ui}</QueryClientProvider>); }

describe("appointment workflow", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("renders the quick appointment form and blocks invalid mobile verification", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    renderWithQuery(<BookingForm quickMode />);
    expect(screen.getByRole("heading", { name: /quick appointment/i })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Patient name"), { target: { value: "Asha Sharma" } });
    fireEvent.change(screen.getByLabelText("Age"), { target: { value: "42" } });
    fireEvent.change(screen.getByLabelText("Gender"), { target: { value: "FEMALE" } });
    fireEvent.change(screen.getByLabelText("Mobile number"), { target: { value: "123" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText(/valid 10-digit/i)).toBeInTheDocument();
  });

  it("uses backend OTP verification and invalidates it when mobile changes", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === "/api/booking-otp/issue") {
        return new Response(JSON.stringify({ verification_id: "verification-1" }), { status: 201 });
      }
      if (url === "/api/booking-otp/verify") {
        const body = JSON.parse(String(init?.body));
        return body.otp === "654321"
          ? new Response(JSON.stringify({ token: "signed-token" }), { status: 200 })
          : new Response(JSON.stringify(["The OTP is invalid."]), { status: 400 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    renderWithQuery(<BookingForm quickMode />);
    fireEvent.change(screen.getByLabelText("Patient name"), { target: { value: "Asha Sharma" } });
    fireEvent.change(screen.getByLabelText("Age"), { target: { value: "42" } });
    fireEvent.change(screen.getByLabelText("Gender"), { target: { value: "FEMALE" } });
    fireEvent.change(screen.getByLabelText("Mobile number"), { target: { value: "9876543210" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    fireEvent.click(await screen.findByRole("button", { name: "Send OTP" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/booking-otp/issue",
      expect.objectContaining({ method: "POST" }),
    ));
    fireEvent.change(screen.getByLabelText("6-digit OTP"), { target: { value: "111111" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify OTP" }));
    expect(await screen.findByText(/OTP is invalid/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("6-digit OTP"), { target: { value: "654321" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify OTP" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/booking-otp/verify",
      expect.objectContaining({ method: "POST" }),
    ));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("Service details")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    fireEvent.change(screen.getByLabelText("Mobile number"), { target: { value: "9876543211" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText(/verify your mobile number/i)).toBeInTheDocument();
  });

  it("renders the owner search and status filters", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    renderWithQuery(<OwnerRequests/>);
    expect(screen.getByRole("heading", { name: "Appointment Requests" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/name, mobile/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Status")).toBeInTheDocument();
  });

  it("advances to service details after valid patient information", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify([{ id: "6a48df41-886b-4512-8408-dd96cf419293", name: "Abhyang", slug: "abhyang" }]), { status: 200 }));
    renderWithQuery(<BookingForm/>);
    fireEvent.change(screen.getByLabelText("Patient name"), { target: { value: "Asha Sharma" } });
    fireEvent.change(screen.getByLabelText("Age"), { target: { value: "42" } });
    fireEvent.change(screen.getByLabelText("Mobile number"), { target: { value: "9876543210" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("Service details")).toBeInTheDocument();
    expect(await screen.findByRole("option", { name: "Abhyang" })).toBeInTheDocument();
  });

  it("renders the customer request module and booking entry point", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    renderWithQuery(<CustomerRequests/>);
    expect(screen.getByRole("heading", { name: "My appointment requests" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Request an appointment" })).toHaveAttribute("href", "/book-appointment");
  });
});
