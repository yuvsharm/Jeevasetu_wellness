import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { emptyServiceAddress, type ServiceAddress } from "@/lib/location/contracts";

import { AddressCapture } from "./address-capture";

function Harness({ initial = emptyServiceAddress(), confirmed = vi.fn() }: { initial?: ServiceAddress; confirmed?: (value: boolean) => void; }) {
  const [value, setValue] = useState(initial);
  return <AddressCapture value={value} onChange={setValue} onConfirmedChange={confirmed} initiallyExpanded={false} />;
}

function provideLocation(accuracy = 111) {
  const getCurrentPosition = vi.fn((success: PositionCallback) => success({ coords: { latitude: 28.61, longitude: 77.21, accuracy } } as GeolocationPosition));
  Object.defineProperty(navigator, "geolocation", { value: { getCurrentPosition }, configurable: true });
  return getCurrentPosition;
}

const googleAddress = {
  address_line_1: "276", address_line_2: "Modipuram", landmark: "", city: "Meerut",
  region: "Uttar Pradesh", pin_code: "250110", display_address: "276, N B Colony, Modipuram, Meerut, Uttar Pradesh 250110, India",
};

describe("AddressCapture", () => {
  afterEach(() => vi.restoreAllMocks());

  it("keeps search feature-gated and requests location only after explicit action", async () => {
    const getCurrentPosition = provideLocation();
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify(googleAddress), { status: 200, headers: { "Content-Type": "application/json" } }));
    render(<Harness />);

    expect(screen.getByPlaceholderText("Search for area, street name, landmark...")).toBeDisabled();
    expect(screen.queryByLabelText("House / Flat / Building")).not.toBeInTheDocument();
    expect(getCurrentPosition).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Use your current location" }));
    expect(await screen.findByText("Location detected")).toBeInTheDocument();
    expect(screen.getByLabelText("House / Flat / Building")).toHaveValue("276");
    expect(screen.getByText("Approx. accuracy: 111 m")).toBeInTheDocument();
    expect(getCurrentPosition).toHaveBeenCalledTimes(1);
  });

  it("accepts a short real house number with blank optional fields and confirms canonical state", async () => {
    provideLocation();
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify(googleAddress), { status: 200, headers: { "Content-Type": "application/json" } }));
    const confirmed = vi.fn();
    render(<Harness confirmed={confirmed} />);
    fireEvent.click(screen.getByRole("button", { name: "Use your current location" }));
    await screen.findByDisplayValue("276");
    expect(screen.getByLabelText("Landmark (optional)")).toHaveValue("");
    fireEvent.change(screen.getByLabelText("Floor / Street / Locality (optional)"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm this address" }));
    expect(await screen.findByText("Address confirmed.")).toBeInTheDocument();
    expect(confirmed).toHaveBeenLastCalledWith(true);
  });

  it("reveals and focuses the shared fields for manual entry, then confirms", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Add address manually" }));
    const house = screen.getByLabelText("House / Flat / Building");
    await waitFor(() => expect(house).toHaveFocus());
    fireEvent.change(house, { target: { value: "12" } });
    fireEvent.change(screen.getByLabelText("City"), { target: { value: "Meerut" } });
    fireEvent.change(screen.getByLabelText("State / Region"), { target: { value: "Uttar Pradesh" } });
    fireEvent.change(screen.getByLabelText("PIN code"), { target: { value: "250004" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm this address" }));
    expect(screen.getByText("Address confirmed.")).toBeInTheDocument();
  });

  it("lets the user complete a partial Google result", async () => {
    provideLocation();
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({ ...googleAddress, address_line_1: "", pin_code: "" }), { status: 200, headers: { "Content-Type": "application/json" } }));
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Use your current location" }));
    expect(await screen.findByText("Please complete the missing required address details.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("House / Flat / Building"), { target: { value: "9" } });
    fireEvent.change(screen.getByLabelText("PIN code"), { target: { value: "250004" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm this address" }));
    expect(screen.getByText("Address confirmed.")).toBeInTheDocument();
  });

  it("invalidates confirmation when the user edits an autofilled value and preserves the edit", async () => {
    provideLocation();
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify(googleAddress), { status: 200, headers: { "Content-Type": "application/json" } }));
    const confirmed = vi.fn();
    render(<Harness confirmed={confirmed} />);
    fireEvent.click(screen.getByRole("button", { name: "Use your current location" }));
    await screen.findByDisplayValue("276");
    fireEvent.click(screen.getByRole("button", { name: "Confirm this address" }));
    expect(confirmed).toHaveBeenLastCalledWith(true);
    fireEvent.change(screen.getByLabelText("House / Flat / Building"), { target: { value: "276 A" } });
    expect(screen.getByLabelText("House / Flat / Building")).toHaveValue("276 A");
    expect(confirmed).toHaveBeenLastCalledWith(false);
  });

  it("does not let a late geocoding response overwrite newer manual edits", async () => {
    let resolveLookup!: (value: Response) => void;
    provideLocation();
    vi.spyOn(global, "fetch").mockReturnValue(new Promise((resolve) => { resolveLookup = resolve; }));
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Use your current location" }));
    fireEvent.click(screen.getByRole("button", { name: "Add address manually" }));
    fireEvent.change(screen.getByLabelText("House / Flat / Building"), { target: { value: "My edited house" } });
    resolveLookup(new Response(JSON.stringify(googleAddress), { status: 200, headers: { "Content-Type": "application/json" } }));
    await waitFor(() => expect(screen.getByLabelText("House / Flat / Building")).toHaveValue("My edited house"));
    expect(screen.queryByDisplayValue("276")).not.toBeInTheDocument();
  });

  it("blocks duplicate geolocation requests", () => {
    const getCurrentPosition = vi.fn();
    Object.defineProperty(navigator, "geolocation", { value: { getCurrentPosition }, configurable: true });
    render(<Harness />);
    const button = screen.getByRole("button", { name: "Use your current location" });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(getCurrentPosition).toHaveBeenCalledTimes(1);
  });

  it.each([
    [1, "Location access was not allowed. Please enter your address manually."],
    [2, "We couldn't detect your location. Please try again or enter your address manually."],
    [3, "We couldn't detect your location. Please try again or enter your address manually."],
  ])("provides manual fallback for geolocation error %s", async (code, expected) => {
    Object.defineProperty(navigator, "geolocation", { value: { getCurrentPosition: (_: PositionCallback, error: PositionErrorCallback) => error({ code } as GeolocationPositionError) }, configurable: true });
    const fetchMock = vi.spyOn(global, "fetch");
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Use your current location" }));
    expect(await screen.findByText(expected)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Add address manually" })).toBeEnabled();
  });

  it.each([
    [503, "NOT_CONFIGURED", "automatic address lookup is not configured"],
    [429, "RATE_LIMITED", "address lookup is temporarily busy"],
    [503, "PROVIDER_UNAVAILABLE", "couldn't identify the complete address"],
  ])("uses a safe manual fallback for lookup failure %s", async (status, code, expected) => {
    provideLocation();
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "secret raw error", code }), { status, headers: { "Content-Type": "application/json" } }));
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Use your current location" }));
    expect(await screen.findByText(new RegExp(expected, "i"))).toBeInTheDocument();
    expect(screen.queryByText("secret raw error")).not.toBeInTheDocument();
    expect(screen.getByLabelText("House / Flat / Building")).toBeInTheDocument();
  });

  it("keeps controls constrained and switches fields from one to two columns responsively", () => {
    render(<Harness initial={{ ...emptyServiceAddress(), address_line_1: "12", city: "Meerut", region: "Uttar Pradesh", pin_code: "250004" }} />);
    expect(screen.getByRole("group", { name: "Service address" })).toHaveClass("min-w-0", "max-w-full");
    expect(screen.getByLabelText("House / Flat / Building")).toHaveClass("w-full", "min-w-0", "max-w-full");
    expect(screen.getByLabelText("House / Flat / Building").closest("div")).toHaveClass("grid", "md:grid-cols-2");
  });
});
