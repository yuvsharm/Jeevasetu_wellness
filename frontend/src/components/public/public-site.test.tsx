import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient,QueryClientProvider } from "@tanstack/react-query";

import ContactPage from "@/app/contact/page";
import Home from "@/app/page";
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
    expect(screen.getAllByRole("link",{name:"Customer Login"})[0]).toHaveAttribute("href","/customer-login");
    expect(screen.getAllByRole("link",{name:"Book Appointment"})[0]).toHaveAttribute("href","/book-appointment");
  });

  it("composes the premium homepage from real catalog and approved review data",async()=>{
    const client=new QueryClient({defaultOptions:{queries:{staleTime:Infinity}}});
    client.setQueryData(["commercial-public"],{therapies:[{id:"therapy-1",name:"Kati Basti",slug:"kati-basti",base_price:"1200.00",short_description:"Focused care",benefits:[],is_active:true,is_publicly_visible:true}],packages:[{id:"package-1",name:"7 Session Plan",therapy:"therapy-1",therapy_name:"Kati Basti",session_count:7,selling_price:"7000.00",regular_total:"8400.00",saving:"1400.00",discount_percentage:16.67,description:"",valid_from:null,valid_until:null,is_active:true,is_publicly_visible:true,display_order:1}],offers:[]});
    client.setQueryData(["public-reviews"],{average_rating:5,review_count:1,reviews:[{stars:5,comment:"Thoughtful home service",customer_display_name:"Asha",physiotherapist_name:"Priya",created_at:"2026-08-20T10:00:00Z"}]});
    render(<QueryClientProvider client={client}><Home/></QueryClientProvider>);
    expect(screen.getByRole("heading",{level:1,name:/physiotherapy & wellness care/i})).toBeInTheDocument();
    expect(screen.getByRole("heading",{name:"Kati Basti"})).toBeInTheDocument();
    expect(screen.getByRole("heading",{name:"7 Session Plan"})).toBeInTheDocument();
    expect(screen.getByText("Thoughtful home service")).toBeInTheDocument();
    expect(screen.getAllByRole("link",{name:"Join With Us"})[0]).toHaveAttribute("href","/work-with-us");
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
