import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { OfflineAppointmentBooking } from "./offline-appointment-booking";

afterEach(() => vi.restoreAllMocks());

it("clears a previous patient before creating a lightweight offline booking", async () => {
  let submitted: Record<string, unknown> | null = null;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/api/session/me")) return json({ access: { permitted_clinics: [{ id: "clinic-1", slug: "meerut" }] } });
    if (url.endsWith("/api/appointment-therapies")) return json([{ id: "therapy-1", name: "Abhyang", slug: "abhyang", default_duration_minutes: 60, base_price: "500.00" }]);
    if (url.includes("/api/staff/profiles")) return json({ count: 1, results: [{ id: "staff-1", full_name: "Farha", therapy_competency_ids: ["therapy-1"], service_area_ids: ["area-1"] }] });
    if (url.endsWith("/api/staff/options")) return json({ service_areas: [{ id: "area-1", name: "Meerut", pin_codes: ["250004"] }] });
    if (url.includes("/api/patients?search=9990000002")) return json({ count: 1, results: [{ id: "patient-1", full_name: "Existing Patient" }] });
    if (url.endsWith("/api/patients/patient-1")) return json({ id: "patient-1", full_name: "Existing Patient", age: 32, gender: "FEMALE", clinic: "clinic-1", addresses: [{ address_line_1: "Old address", address_line_2: "", landmark: "", city: "Meerut", region: "Uttar Pradesh", pin_code: "250004", is_active: true, is_primary: true }] });
    if (url.includes("/api/patients?search=9990000099")) return json({ count: 0, results: [] });
    if (url.includes("/api/schedule/available-physiotherapists")) return json([{ id: "staff-1", full_name: "Farha" }]);
    if (url.endsWith("/api/commercial/quote")) return json({ final_amount: "500.00", duration_minutes: 60 });
    if (url.endsWith("/api/owner/offline-appointments") && init?.method === "POST") {
      submitted = JSON.parse(String(init.body));
      return json({ id: "appointment-1", patient_reused: false, patient_id: "patient-2", booking_source: "REFERRAL", payment_status: "PENDING", payment_amount_due: "500.00" }, 201);
    }
    return json({});
  });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><OfflineAppointmentBooking /></QueryClientProvider>);

  fireEvent.change(screen.getByLabelText("Mobile number"), { target: { value: "9990000002" } });
  fireEvent.click(screen.getByRole("button", { name: "Search mobile" }));
  expect(await screen.findByDisplayValue("Existing Patient")).toBeDisabled();
  expect(screen.getByDisplayValue("Old address")).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Mobile number"), { target: { value: "9990000099" } });
  fireEvent.click(screen.getByRole("button", { name: "Search mobile" }));
  await screen.findByText("No patient found. Enter lightweight patient details below.");
  await waitFor(() => expect(screen.getByLabelText("Customer / patient name")).toHaveValue(""));
  expect(screen.getByLabelText("House / Flat / Building")).toHaveValue("");

  fireEvent.change(screen.getByLabelText("Customer / patient name"), { target: { value: "Fresh Offline Patient" } });
  fireEvent.change(screen.getByLabelText("Age"), { target: { value: "40" } });
  fireEvent.change(screen.getByLabelText("Gender"), { target: { value: "FEMALE" } });
  fireEvent.change(screen.getByLabelText("House / Flat / Building"), { target: { value: "21 Civil Lines" } });
  fireEvent.change(screen.getByLabelText("City"), { target: { value: "Meerut" } });
  fireEvent.change(screen.getByLabelText("PIN code"), { target: { value: "250004" } });
  fireEvent.click(screen.getByRole("button", { name: "Confirm this address" }));
  fireEvent.click(screen.getByLabelText("Abhyang"));
  fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-09-20" } });
  fireEvent.change(screen.getByLabelText("Time"), { target: { value: "10:00" } });
  await screen.findByText("Current authoritative amount: ₹500.00 · 60 minutes");
  fireEvent.change(screen.getByLabelText("Eligible therapist"), { target: { value: "staff-1" } });
  fireEvent.change(screen.getByLabelText("Booking source"), { target: { value: "REFERRAL" } });
  fireEvent.click(screen.getByRole("button", { name: "Create canonical appointment" }));

  await waitFor(() => expect(submitted).toMatchObject({
    mobile_number: "9990000099",
    patient_name: "Fresh Offline Patient",
    therapies: ["therapy-1"],
    physiotherapist: "staff-1",
    booking_source: "REFERRAL",
  }));
  expect(await screen.findByText("Appointment created successfully.")).toBeInTheDocument();
});

function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status });
}
