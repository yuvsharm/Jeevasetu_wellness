import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CommercialManagement } from "@/components/appointments/commercial-management";

const therapies = [
  { id: "therapy-1", name: "Kati Basti", slug: "kati-basti", short_description: "Focused care", benefits: [], default_duration_minutes: 45, base_price: "1200.00", is_active: true, is_publicly_visible: true, display_order: 1 },
  { id: "therapy-2", name: "Abhyang", slug: "abhyang", short_description: "Full body care", benefits: [], default_duration_minutes: 45, base_price: "1500.00", is_active: true, is_publicly_visible: true, display_order: 2 },
  { id: "therapy-leg", name: "Leg Massage", slug: "leg-massage", short_description: "Promotional add-on", benefits: [], default_duration_minutes: 15, base_price: "0.00", is_active: true, is_publicly_visible: false, is_offer_free_addon: true, display_order: 900 },
  { id: "therapy-head", name: "Head Massage", slug: "head-massage", short_description: "Promotional add-on", benefits: [], default_duration_minutes: 15, base_price: "0.00", is_active: true, is_publicly_visible: false, is_offer_free_addon: true, display_order: 901 },
];
const offer = {
  id: "offer-1", title: "September Offer", promotional_text: "", offer_type: "PERCENTAGE",
  eligible_therapies: ["therapy-1"], eligible_therapy_names: ["Kati Basti"], qualifying_package: null,
  minimum_therapy_count: 1, maximum_therapy_count: null, discount_value: "10", fixed_price: null,
  free_therapy: null, free_therapy_name: "", free_quantity: 1, family_required: false,
  minimum_family_members: 1, rule_config: { discount_type: "PERCENTAGE" },
  valid_from: "2027-09-01T02:30:00Z", valid_until: "2027-09-15T18:29:00Z",
  is_active: true, is_publicly_visible: true, display_order: 0,
  can_delete: true, protected_references: {},
};

function renderManagement() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><CommercialManagement /></QueryClientProvider>);
}

function mockApi(postResponse: Promise<Response> = Promise.resolve(new Response(JSON.stringify(offer), { status: 201 })), initialOffers: typeof offer[] = []) {
  let storedOffers = [...initialOffers];
  return vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.includes("therapies")) return new Response(JSON.stringify(therapies), { status: 200 });
    if (url.includes("packages")) return new Response(JSON.stringify([]), { status: 200 });
    if (url === "/api/commercial/offers" && init?.method === "POST") {
      const response = await postResponse;
      storedOffers = [await response.clone().json() as typeof offer, ...storedOffers];
      return response;
    }
    if (url.startsWith("/api/commercial/offers/") && init?.method === "PATCH") {
      const id = url.split("/").at(-1);
      const changes = JSON.parse(String(init.body));
      const saved = { ...storedOffers.find((item) => item.id === id)!, ...changes };
      storedOffers = storedOffers.map((item) => item.id === id ? saved : item);
      return new Response(JSON.stringify(saved), { status: 200 });
    }
    if (url.startsWith("/api/commercial/offers/") && init?.method === "DELETE") {
      const id = url.split("/").at(-1);
      storedOffers = storedOffers.filter((item) => item.id !== id);
      return new Response(null, { status: 204 });
    }
    if (url === "/api/commercial/offers") return new Response(JSON.stringify(storedOffers), { status: 200 });
    return new Response(JSON.stringify([]), { status: 200 });
  });
}

function choose(name: string) {
  fireEvent.click(screen.getByText(name, { exact: true }).closest("label")!);
}

describe("CommercialManagement", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows only fields relevant to each offer type", async () => {
    mockApi();
    renderManagement();
    expect(screen.queryByLabelText("Offer Name")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Create New Offer" }));
    await screen.findByRole("checkbox", { name: "Kati Basti" });

    expect(screen.getByLabelText("Discount Percentage (%)")).toBeInTheDocument();
    expect(screen.queryByLabelText("Discount Amount (₹)")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Get This Therapy FREE")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Minimum Eligible Therapies")).toBeInTheDocument();
    expect(screen.queryByText(/maximum therapy count/i)).not.toBeInTheDocument();

    choose("Fixed ₹ Discount");
    expect(screen.getByLabelText("Discount Amount (₹)")).toBeInTheDocument();
    expect(screen.queryByLabelText("Discount Percentage (%)")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Minimum Family Members")).not.toBeInTheDocument();

    choose("Combo Discount");
    expect(screen.getByText("Combo Benefit")).toBeInTheDocument();
    expect(screen.getByLabelText("Combo Discount (%)")).toBeInTheDocument();
    choose("Final Combo Price ₹");
    expect(screen.getByLabelText("Final Combo Price (₹)")).toBeInTheDocument();
    expect(screen.queryByLabelText("Combo Discount (%)")).not.toBeInTheDocument();

    choose("Buy Therapies + Get Therapy Free");
    const buyFreeSelector = screen.getByLabelText("Get This Therapy FREE");
    expect(within(buyFreeSelector).getByRole("option", { name: "Leg Massage" })).toBeInTheDocument();
    expect(within(buyFreeSelector).getByRole("option", { name: "Head Massage" })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "Leg Massage" })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "Head Massage" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Discount Amount (₹)")).not.toBeInTheDocument();

    choose("Family Offer");
    expect(screen.getByLabelText("Minimum Family Members")).toBeInTheDocument();
    expect(screen.getByLabelText("Family Discount (%)")).toBeInTheDocument();
    choose("Free therapy");
    const familyFreeSelector = screen.getByLabelText("Get This Therapy FREE");
    expect(within(familyFreeSelector).getByRole("option", { name: "Leg Massage" })).toBeInTheDocument();
    expect(within(familyFreeSelector).getByRole("option", { name: "Head Massage" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Family Discount (%)")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close Create Form" }));
    expect(screen.queryByLabelText("Offer Name")).not.toBeInTheDocument();
  });

  it("shows exact field-level validation instead of silently failing", async () => {
    mockApi();
    renderManagement();
    fireEvent.click(screen.getByRole("button", { name: "Create New Offer" }));
    fireEvent.change(await screen.findByLabelText("Offer Name"), { target: { value: "September Offer" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Offer" }));
    expect(await screen.findByText("Please select at least one therapy.")).toHaveAttribute("role", "alert");
    expect(screen.getByText("Please enter the discount percentage.")).toHaveAttribute("role", "alert");
    expect(screen.getByText("Please select the offer start date.")).toHaveAttribute("role", "alert");
  });

  it("creates an offer, shows progress and reports success", async () => {
    let release!: (response: Response) => void;
    const pending = new Promise<Response>((resolve) => { release = resolve; });
    const fetchMock = mockApi(pending);
    renderManagement();
    fireEvent.click(screen.getByRole("button", { name: "Create New Offer" }));
    fireEvent.change(await screen.findByLabelText("Offer Name"), { target: { value: "September Offer" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Kati Basti" }));
    fireEvent.change(screen.getByLabelText("Discount Percentage (%)"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText("Start Date"), { target: { value: "2027-09-01" } });
    fireEvent.change(screen.getByLabelText("End Date"), { target: { value: "2027-09-15" } });
    const createButton = screen.getByRole("button", { name: "Create Offer" });
    fireEvent.click(createButton);
    fireEvent.click(createButton);
    expect(await screen.findByRole("button", { name: "Creating..." })).toBeDisabled();
    release(new Response(JSON.stringify(offer), { status: 201 }));
    expect(await screen.findByText("Offer created successfully.")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Done ✓" })).toBeDisabled();
    expect(screen.getByLabelText("Offer Name")).toHaveValue("");
    expect(screen.getByLabelText("Discount Percentage (%)")).toHaveValue(null);
    expect(screen.getByRole("checkbox", { name: "Kati Basti" })).not.toBeChecked();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/commercial/offers", expect.objectContaining({ method: "POST" })));
    expect(fetchMock.mock.calls.filter(([input, init]) => String(input) === "/api/commercial/offers" && init?.method === "POST")).toHaveLength(1);
    const createCall = fetchMock.mock.calls.find(([input, init]) => String(input) === "/api/commercial/offers" && init?.method === "POST");
    expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
      valid_from: "2027-08-31T18:30:00.000Z",
      valid_until: "2027-09-15T18:30:00.000Z",
      minimum_therapy_count: 1,
    });
    expect(screen.getAllByText("September Offer")).toHaveLength(1);
    expect(screen.getByRole("heading", { name: "Archived Offers" })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByLabelText("Offer Name")).not.toBeInTheDocument(), { timeout: 3500 });
  });

  it("renders all owner status groups as compact rows and explains protected deletion", async () => {
    const now = Date.now();
    const active = { ...offer, id: "active", title: "Active Care", valid_from: new Date(now - 60_000).toISOString(), valid_until: new Date(now + 86_400_000).toISOString(), can_delete: false };
    const upcoming = { ...offer, id: "upcoming", title: "Upcoming Care", valid_from: new Date(now + 86_400_000).toISOString(), valid_until: new Date(now + 172_800_000).toISOString() };
    const expired = { ...offer, id: "expired", title: "Expired Care", valid_from: new Date(now - 172_800_000).toISOString(), valid_until: new Date(now - 86_400_000).toISOString() };
    const archived = { ...offer, id: "archived", title: "Archived Care", is_active: false, valid_from: new Date(now - 60_000).toISOString(), valid_until: new Date(now + 86_400_000).toISOString() };
    mockApi(undefined, [active, upcoming, expired, archived]);
    renderManagement();
    expect(await screen.findByText("Active Care")).toBeInTheDocument();
    expect(screen.getByText("Upcoming Care")).toBeInTheDocument();
    expect(screen.getByText("Expired Care")).toBeInTheDocument();
    expect(screen.getByText("Archived Care")).toBeInTheDocument();
    expect(screen.queryByText("Eligible therapies")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Active Care").closest("button")!);
    expect(screen.getByText("Eligible therapies")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Upcoming Care").closest("button")!);
    expect(screen.getAllByText("Eligible therapies")).toHaveLength(1);
    fireEvent.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    expect(screen.getByText("This offer has historical booking records and cannot be permanently deleted. Archive it instead.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    const activeRow = screen.getByText("Active Care").closest("article")!;
    fireEvent.click(within(activeRow).getByRole("button", { name: "Deactivate" }));
    fireEvent.click(within(screen.getByRole("dialog", { name: "Deactivate this offer?" })).getByRole("button", { name: "Deactivate" }));
    expect(await screen.findByText("Offer deactivated successfully.")).toBeInTheDocument();
    await waitFor(() => expect(within(screen.getByRole("heading", { name: "Archived Offers" }).closest("section")!).getByText("Active Care")).toBeInTheDocument());

    const upcomingRow = screen.getByText("Upcoming Care").closest("article")!;
    fireEvent.click(within(upcomingRow).getByRole("button", { name: "Delete" }));
    fireEvent.click(within(screen.getByRole("dialog", { name: "Delete this offer permanently?" })).getByRole("button", { name: "Delete permanently" }));
    expect(await screen.findByText("Offer deleted successfully.")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Upcoming Care")).not.toBeInTheDocument());
  });
});
