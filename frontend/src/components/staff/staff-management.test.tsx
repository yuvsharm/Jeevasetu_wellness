import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ManagerDashboard, PhysiotherapistProfile, StaffDirectory } from "@/components/staff/staff-management";

const profile = { id:"1",user_id:"2",staff_type:"PHYSIOTHERAPIST",full_name:"Dr Asha Sharma",email:"asha@example.com",mobile:"+919876543210",profile_photo:"",gender:"FEMALE",date_of_birth:"1990-01-01",qualification:"BPT",registration_number:"REG-1",experience_years:8,specialization_ids:[],languages_known:["Hindi"],alternate_mobile:"",emergency_contact:"9876543211",current_address:"Meerut",city:"Meerut",pin_code:"250004",clinic:"clinic-1",service_area_ids:["area-1"],availability:"AVAILABLE",is_online:true,joining_date:"2026-01-01",is_active:true,bio:"",documents:[] };
function wrap(ui:React.ReactNode){return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}>{ui}</QueryClientProvider>)}

describe("staff management",()=>{
  beforeEach(()=>vi.restoreAllMocks());
  it("provides owner search, filters, sorting and staff form",()=>{vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify({count:0,next:null,previous:null,results:[]}),{status:200}));wrap(<StaffDirectory allowManagers/>);expect(screen.getByLabelText("Search staff")).toBeInTheDocument();expect(screen.getByLabelText("Filter role")).toBeInTheDocument();expect(screen.getByLabelText("Sort staff")).toBeInTheDocument();fireEvent.click(screen.getByRole("button",{name:"Add staff member"}));expect(screen.getByRole("form",{name:"Create staff profile"})).toBeInTheDocument();});
  it("shows manager operational counts without fabricated appointment values",async()=>{vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify({count:1,next:null,previous:null,results:[profile]}),{status:200}));wrap(<ManagerDashboard/>);expect(await screen.findByText("Total Physiotherapists")).toBeInTheDocument();expect(screen.getByText("Today's appointments")).toBeInTheDocument();});
  it("shows the physiotherapist self profile and availability controls",async()=>{vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify(profile),{status:200}));wrap(<PhysiotherapistProfile/>);expect(await screen.findByText("Dr Asha Sharma")).toBeInTheDocument();expect(screen.getByLabelText("Availability")).toHaveValue("AVAILABLE");expect(screen.getByRole("button",{name:"Go offline"})).toBeInTheDocument();});
});
