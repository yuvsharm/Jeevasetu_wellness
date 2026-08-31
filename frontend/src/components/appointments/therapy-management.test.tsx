import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TherapyManagement } from "@/components/appointments/therapy-management";

const base = {
  slug: "", short_description: "", detailed_description: "", benefits: [], default_duration_minutes: 45,
  base_price: "1500.00", is_active: true, is_publicly_visible: true, display_order: 1,
  can_delete: false, protected_references: { appointments: 1 },
};
const initial = [
  { ...base, id: "therapy-1", name: "Abhyang", slug: "abhyang", short_description: "Traditional oil therapy", detailed_description: "Performed with warm oil.", benefits: ["Relaxation"] },
  { ...base, id: "therapy-2", name: "Potli Massage", slug: "potli-massage", base_price: "1800.00", short_description: "Herbal compress therapy", detailed_description: "Performed with a warm herbal potli." },
  { ...base, id: "therapy-3", name: "Nasya", slug: "nasya", is_active: false, is_publicly_visible: false, can_delete: true, protected_references: {} },
];

function setup() {
  let therapies = [...initial];
  const fetchMock = vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url === "/api/commercial/therapies" && (!init?.method || init.method === "GET")) return new Response(JSON.stringify(therapies), { status: 200 });
    if (url === "/api/commercial/therapies" && init?.method === "POST") {
      const body = JSON.parse(String(init.body));
      const created = { ...base, ...body, id: "therapy-new", can_delete: true, protected_references: {} };
      therapies = [created, ...therapies];
      return new Response(JSON.stringify(created), { status: 201 });
    }
    const id = url.split("/").filter(Boolean).at(-1)!;
    if (init?.method === "PATCH") {
      const body = JSON.parse(String(init.body));
      const current = therapies.find((therapy) => therapy.id === id)!;
      const updated = { ...current, ...body };
      therapies = therapies.map((therapy) => therapy.id === id ? updated : therapy);
      return new Response(JSON.stringify(updated), { status: 200 });
    }
    if (init?.method === "DELETE") {
      therapies = therapies.filter((therapy) => therapy.id !== id);
      return new Response(null, { status: 204 });
    }
    if (url === "/api/commercial/public") return new Response(JSON.stringify({ therapies: [], packages: [], offers: [] }), { status: 200 });
    return new Response(JSON.stringify([]), { status: 200 });
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><TherapyManagement /></QueryClientProvider>);
  return fetchMock;
}

describe("TherapyManagement", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders compact rows and expands only one therapy inline", async () => {
    setup();
    expect(await screen.findByText("Abhyang")).toBeInTheDocument();
    expect(screen.getByText("Potli Massage")).toBeInTheDocument();
    expect(screen.queryByText("Traditional oil therapy")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Expand Abhyang" }));
    expect(screen.getByText("Traditional oil therapy")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Expand Potli Massage" }));
    expect(screen.queryByText("Traditional oil therapy")).not.toBeInTheDocument();
    expect(screen.getByText("Herbal compress therapy")).toBeInTheDocument();
  });

  it("supports search and active/inactive filters", async () => {
    setup();
    await screen.findByText("Abhyang");
    fireEvent.change(screen.getByLabelText("Search therapies"), { target: { value: "potli" } });
    expect(screen.getByText("Potli Massage")).toBeInTheDocument();
    expect(screen.queryByText("Abhyang")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search therapies"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Inactive" }));
    expect(screen.getByText("Nasya")).toBeInTheDocument();
    expect(screen.queryByText("Abhyang")).not.toBeInTheDocument();
  });

  it("adds, edits, deactivates, reactivates and safely deletes without duplicates", async () => {
    const fetchMock = setup();
    await screen.findByText("Abhyang");
    const protectedRow = screen.getByText("Abhyang").closest("article")!;
    expect(Array.from(protectedRow.querySelectorAll("button")).some((button) => button.textContent === "Delete")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "+ Add Therapy" }));
    fireEvent.change(screen.getByLabelText("Therapy Name"), { target: { value: "Test Therapy" } });
    expect(screen.getByLabelText("URL Slug")).toHaveValue("test-therapy");
    fireEvent.change(screen.getByLabelText("Price (₹)"), { target: { value: "900" } });
    fireEvent.click(screen.getByRole("button", { name: "Add Therapy" }));
    expect(await screen.findByText("Therapy added successfully.")).toBeInTheDocument();
    expect(screen.getByText("Test Therapy")).toBeInTheDocument();

    const newRow = screen.getByText("Test Therapy").closest("article")!;
    fireEvent.click(newRow.querySelector("button")!);
    fireEvent.change(screen.getByLabelText("Therapy Name"), { target: { value: "Updated Test Therapy" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));
    expect(await screen.findByText("Therapy updated successfully.")).toBeInTheDocument();
    expect(screen.getAllByText("Updated Test Therapy")).toHaveLength(1);

    const abhyangRow = screen.getByText("Abhyang").closest("article")!;
    fireEvent.click(Array.from(abhyangRow.querySelectorAll("button")).find((button) => button.textContent === "Deactivate")!);
    const deactivateDialog = screen.getByRole("dialog", { name: "Deactivate Abhyang?" });
    fireEvent.click(Array.from(deactivateDialog.querySelectorAll("button")).find((button) => button.textContent === "Deactivate")!);
    expect(await screen.findByText("Therapy deactivated successfully.")).toBeInTheDocument();
    const deactivatedRow = screen.getByText("Abhyang").closest("article")!;
    fireEvent.click(Array.from(deactivatedRow.querySelectorAll("button")).find((button) => button.textContent === "Reactivate")!);
    expect(await screen.findByText("Therapy activated successfully.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Inactive" }));
    const nasyaRow = screen.getByText("Nasya").closest("article")!;
    fireEvent.click(Array.from(nasyaRow.querySelectorAll("button")).find((button) => button.textContent === "Delete")!);
    const deleteDialog = screen.getByRole("dialog", { name: "Delete Nasya?" });
    fireEvent.click(Array.from(deleteDialog.querySelectorAll("button")).find((button) => button.textContent === "Delete")!);
    expect(await screen.findByText("Therapy deleted successfully.")).toBeInTheDocument();
    expect(screen.queryByText("Nasya")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith("/therapy-3") && init?.method === "DELETE")).toBe(true);
  });
});
