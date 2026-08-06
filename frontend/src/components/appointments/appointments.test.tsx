import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BookingForm } from "@/components/appointments/booking-form";
import { CustomerRequests } from "@/components/appointments/customer-requests";
import { OwnerRequests } from "@/components/appointments/owner-requests";

function renderWithQuery(ui: React.ReactNode) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>{ui}</QueryClientProvider>); }

describe("appointment workflow", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("renders the accessible four-step booking form and blocks invalid patient details", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    renderWithQuery(<BookingForm/>);
    expect(screen.getByRole("list", { name: "Booking progress" })).toHaveTextContent("4. Confirm");
    fireEvent.change(screen.getByLabelText("Patient name"), { target: { value: "A" } });
    fireEvent.change(screen.getByLabelText("Mobile number"), { target: { value: "123" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText(/expected string to have/i)).toBeInTheDocument();
    expect(screen.getByText(/valid 10-digit/i)).toBeInTheDocument();
    expect(screen.getByText("Patient information")).toBeInTheDocument();
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
