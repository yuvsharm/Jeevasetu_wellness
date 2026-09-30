import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient,QueryClientProvider } from "@tanstack/react-query";

import ContactPage from "@/app/contact/page";
import Home from "@/app/page";
import TherapiesPage from "@/app/therapies/page";
import { getTherapyMedia } from "@/lib/public-site/therapy-media";
import { PublicHeader } from "./public-header";

const productionTherapyNames=["Abhyang","Potli Massage","Shirodhara","Basti","Jannu Basti","Kati Basti","Griva Basti","Akshiyarpah (Both Eyes)","Nasya","Deeptishu Massage"];
const productionTherapies=productionTherapyNames.map((name,index)=>({id:`therapy-${index+1}`,name,slug:name.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/(^-|-$)/g,""),base_price:`${500+index*100}.00`,default_duration_minutes:45,short_description:`Approved information for ${name}`,benefits:[],is_active:true,is_publicly_visible:true,display_order:index+1}));

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
    const customerAccess = screen.getByRole("navigation", { name: "Customer access" });
    expect(within(customerAccess).getByRole("link", { name: "Login" })).toHaveAttribute("href", "/customer-login");
    expect(within(customerAccess).getByRole("link", { name: "Register" })).toHaveAttribute("href", "/customer-register");
    const toggle = screen.getByRole("button", { name: /toggle navigation/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("navigation", { name: /mobile navigation/i })).toBeInTheDocument();
    expect(screen.getAllByRole("link",{name:"Customer Login"})[0]).toHaveAttribute("href","/customer-login");
    expect(screen.getAllByRole("link",{name:"Customer Register"})[0]).toHaveAttribute("href","/customer-register");
    expect(screen.getAllByRole("link",{name:"Staff Login"})[0]).toHaveAttribute("href","/login");
    expect(screen.getAllByRole("link",{name:"Book Appointment"})[0]).toHaveAttribute("href","/customer-access?returnTo=%2Fbook-appointment");
  });

  it("shows all ten backend therapies as compact directly bookable cards",async()=>{
    const client=new QueryClient({defaultOptions:{queries:{staleTime:Infinity}}});
    client.setQueryData(["commercial-public"],{therapies:productionTherapies,packages:[],offers:[]});
    client.setQueryData(["public-reviews"],{average_rating:null,review_count:0,reviews:[]});
    client.setQueryData(["public-practitioners"],[]);
    render(<QueryClientProvider client={client}><Home/></QueryClientProvider>);
    for(const [index,name] of productionTherapyNames.entries()){
      expect(screen.getByRole("heading",{name})).toBeInTheDocument();
      expect(screen.getByRole("link",{name:`Book ${name}`})).toHaveAttribute("href",`/book-appointment?therapy=therapy-${index+1}`);
      expect(screen.getByRole("link",{name:`View details for ${name}`})).toHaveAttribute("href",expect.stringMatching(/^\/therapies#/));
      expect(screen.getByAltText(getTherapyMedia(productionTherapies[index].slug,name).alt)).toBeInTheDocument();
    }
    expect(screen.queryByText(/Runtime OTP Primary Therapy/i)).not.toBeInTheDocument();
    expect(screen.getByRole("heading",{name:"Login/Register & request booking"})).toBeInTheDocument();
    expect(screen.getByRole("heading",{name:"NuriPain Ease confirms your professional"})).toBeInTheDocument();
    expect(screen.queryByRole("heading",{name:"Manager confirms therapist"})).not.toBeInTheDocument();
  });

  it("composes the premium homepage from real catalog and approved review data",async()=>{
    const client=new QueryClient({defaultOptions:{queries:{staleTime:Infinity}}});
    client.setQueryData(["commercial-public"],{therapies:[{id:"therapy-1",name:"Kati Basti",slug:"kati-basti",base_price:"1200.00",short_description:"Focused care",benefits:[],is_active:true,is_publicly_visible:true}],packages:[{id:"package-1",name:"7 Session Plan",therapy:"therapy-1",therapy_name:"Kati Basti",session_count:7,selling_price:"7000.00",regular_total:"8400.00",saving:"1400.00",discount_percentage:16.67,description:"",valid_from:null,valid_until:null,is_active:true,is_publicly_visible:true,display_order:1}],offers:[]});
    client.setQueryData(["public-reviews"],{average_rating:5,review_count:1,reviews:[{stars:5,comment:"Thoughtful home service",customer_display_name:"Asha",physiotherapist_name:"Priya",created_at:"2026-08-20T10:00:00Z"}]});
    client.setQueryData(["public-practitioners"],[]);
    render(<QueryClientProvider client={client}><Home/></QueryClientProvider>);
    expect(screen.getByRole("heading",{level:1,name:/physiotherapy & wellness care/i})).toBeInTheDocument();
    expect(screen.getByRole("heading",{name:"Kati Basti"})).toBeInTheDocument();
    expect(screen.getByRole("heading",{name:"7 Session Plan"})).toBeInTheDocument();
    expect(screen.getByText("Thoughtful home service")).toBeInTheDocument();
    const bookingLinks=screen.getAllByRole("link",{name:"Book Appointment"});
    expect(bookingLinks).toHaveLength(2);
    for (const bookingLink of bookingLinks) expect(bookingLink).toHaveAttribute("href","/customer-access?returnTo=%2Fbook-appointment");
    expect(screen.getAllByRole("link", { name: "Customer Login" }).length).toBeGreaterThanOrEqual(2);
    for (const registerLink of screen.getAllByRole("link", { name: "Register" })) expect(registerLink).toHaveAttribute("href", "/customer-register");
    expect(screen.getByRole("link",{name:"Explore Therapies"})).toHaveAttribute("href","#therapies");
    const therapistsHeading=screen.getByRole("heading",{name:"Available Therapists"});
    expect(screen.getByRole("heading",{name:"Kati Basti"}).compareDocumentPosition(therapistsHeading)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(therapistsHeading.compareDocumentPosition(screen.getByRole("heading",{name:"7 Session Plan"}))&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const professionalHeading=screen.getByRole("heading",{name:"Grow your practice with NuriPain Ease"});
    const journeyHeading=screen.getByRole("heading",{name:"From your first choice to a verified home visit"});
    expect(professionalHeading.compareDocumentPosition(journeyHeading)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByRole("img",{name:"NuriPain Ease physiotherapist preparing for a professional home-care visit"})).toBeInTheDocument();
    expect(screen.getByRole("link",{name:"Apply to Join"})).toHaveAttribute("href","/work-with-us");
    expect(screen.getByRole("link",{name:"Professional Login"})).toHaveAttribute("href","/login");
    expect(screen.queryByRole("heading",{name:"Join NuriPain Ease as a Professional"})).not.toBeInTheDocument();
    expect(screen.getByRole("heading",{name:"Questions before you book?"})).toBeInTheDocument();
    expect(screen.getByText("Appointment slots are available during configured service hours.")).toBeInTheDocument();
    expect(screen.queryByText("Appointment slots are coordinated between 9 AM and 6 PM.")).not.toBeInTheDocument();
  });

  it("shows real contact information and a safe enquiry acknowledgement", async () => {
    render(<ContactPage />);
    expect(screen.getAllByText("9084401814").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Email NuriPain Ease").length).toBeGreaterThan(0);
    await userEvent.type(screen.getByLabelText("Name"), "Test Guest");
    await userEvent.type(screen.getByLabelText("Phone"), "9999999999");
    await userEvent.type(screen.getByLabelText(/how can we help/i), "Please share availability.");
    await userEvent.click(screen.getByRole("button", { name: /send enquiry/i }));
    expect(screen.getByRole("status")).toHaveTextContent(/thank you/i);
  });
});
