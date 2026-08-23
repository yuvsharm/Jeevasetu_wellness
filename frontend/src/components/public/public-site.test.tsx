import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient,QueryClientProvider } from "@tanstack/react-query";

import ContactPage from "@/app/contact/page";
import TherapiesPage from "@/app/therapies/page";
import { PublicHeader } from "./public-header";

describe("public website", () => {
  it("publishes only backend-managed visible therapies and current fees", async () => {
    const client=new QueryClient({defaultOptions:{queries:{staleTime:Infinity}}});
    client.setQueryData(["commercial-public"],{therapies:[{id:"therapy-1",name:"Kati Basti",slug:"kati-basti",base_price:"1200.00",short_description:"Focused care",benefits:[],is_active:true,is_publicly_visible:true}],packages:[],offers:[]});
    render(<QueryClientProvider client={client}><TherapiesPage /></QueryClientProvider>);
    expect(await screen.findByRole("heading", { name:"Kati Basti" })).toBeInTheDocument();
    expect(screen.getByText("₹1,200")).toBeInTheDocument();
    expect(screen.queryByText("Abhyang")).not.toBeInTheDocument();
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
