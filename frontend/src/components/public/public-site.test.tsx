import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ContactPage from "@/app/contact/page";
import TherapiesPage from "@/app/therapies/page";
import { PublicHeader } from "./public-header";

describe("public website", () => {
  it("publishes exactly the approved ten therapies and fees", () => {
    render(<TherapiesPage />);
    const names = ["Abhyang", "Potli Massage", "Shirodhara", "Basti", "Jannu Basti", "Kati Basti", "Griva Basti", "Akshiyarpah (Both Eyes)", "Nasya", "Deeptishu Massage"];
    for (const name of names) expect(screen.getByRole("heading", { name })).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(10);
    for (const fee of ["₹500", "₹600", "₹1800", "₹2000", "₹1900", "₹1500", "₹1000", "₹800"]) expect(screen.getAllByText(fee).length).toBeGreaterThan(0);
  });

  it("provides keyboard-accessible mobile navigation", async () => {
    render(<PublicHeader />);
    const toggle = screen.getByRole("button", { name: /toggle navigation/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("navigation", { name: /mobile navigation/i })).toBeInTheDocument();
  });

  it("shows real contact information and a safe enquiry acknowledgement", async () => {
    render(<ContactPage />);
    expect(screen.getAllByText("9084401814").length).toBeGreaterThan(0);
    expect(screen.getAllByText("jeevasetu21@gmail.com").length).toBeGreaterThan(0);
    await userEvent.type(screen.getByLabelText("Name"), "Test Guest");
    await userEvent.type(screen.getByLabelText("Phone"), "9999999999");
    await userEvent.type(screen.getByLabelText(/how can we help/i), "Please share availability.");
    await userEvent.click(screen.getByRole("button", { name: /send enquiry/i }));
    expect(screen.getByRole("status")).toHaveTextContent(/thank you/i);
  });
});
