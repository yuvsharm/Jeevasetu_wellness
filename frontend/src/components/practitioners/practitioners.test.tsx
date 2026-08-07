import {QueryClient,QueryClientProvider} from "@tanstack/react-query";
import {render,screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {beforeEach,describe,expect,it,vi} from "vitest";

import {EnrollmentForm} from "@/components/practitioners/enrollment-form";
import {OpenToWorkControl} from "@/components/practitioners/open-to-work";
import {PublicPractitionerDirectory} from "@/components/practitioners/public-directory";

function wrap(ui:React.ReactNode){return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}>{ui}</QueryClientProvider>)}

describe("practitioner enrollment",()=>{
  beforeEach(()=>vi.restoreAllMocks());
  it("shows the six-step enrollment with structured personal fields",async()=>{vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify([]),{status:200}));wrap(<EnrollmentForm/>);expect(await screen.findByLabelText("Enrollment progress")).toBeInTheDocument();expect(screen.getByText(/6. Review & Submit/)).toBeInTheDocument();expect(screen.getByLabelText("Full legal name")).toBeInTheDocument();});
  it("renders only safe verified directory information",async()=>{vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify([{id:"1",display_name:"Dr Asha Sharma",category:"PHYSIOTHERAPIST",highest_qualification:"MPT",qualification_specialization:"Orthopaedic",experience_years:9,languages:["Hindi"],bio:"Home service specialist",service_area:"Meerut",verified_services:["Physiotherapy"],photo_url:""}]),{status:200}));wrap(<PublicPractitionerDirectory/>);expect(await screen.findByText("Dr Asha Sharma")).toBeInTheDocument();expect(screen.getByText("JeevaSetu Verified")).toBeInTheDocument();expect(screen.queryByText(/email|mobile|government/i)).not.toBeInTheDocument();});
  it("provides an explicit Open to Work switch",async()=>{vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify({is_open_to_work:true}),{status:200}));wrap(<OpenToWorkControl/>);const control=screen.getByRole("switch");expect(control).toHaveAttribute("aria-checked","false");await userEvent.click(control);expect(await screen.findByRole("switch")).toHaveAttribute("aria-checked","true");});
});
