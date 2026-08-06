import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AssignedAppointments, CustomerAppointments, ScheduleOperations } from "@/components/appointments/operational-schedule";

function wrap(ui:React.ReactNode){return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}>{ui}</QueryClientProvider>)}
const appointment={id:"a1",patient_identifier:"PAT-000001",patient_name:"Asha Sharma",therapy_name:"Physiotherapy",clinic_name:"Meerut",scheduled_start:"2026-08-08T10:00:00+05:30",scheduled_end:"2026-08-08T11:00:00+05:30",duration_minutes:60,status:"CONFIRMED",physiotherapist_name:"Dr Physio User",address_line_1:"Shastri Nagar",city:"Meerut",pin_code:"250004",physiotherapist_photo_url:null};

describe("operational scheduling",()=>{
  beforeEach(()=>vi.restoreAllMocks());
  it("provides operations filters and an explicit appointment form",()=>{vi.spyOn(global,"fetch").mockImplementation(async input=>{const url=String(input);const value=url.includes("appointment-therapies")?[]:url.includes("session/me")?{access:{permitted_clinics:[]}}:{count:0,next:null,previous:null,results:[]};return new Response(JSON.stringify(value),{status:200})});wrap(<ScheduleOperations/>);expect(screen.getByLabelText("Filter appointment status")).toBeInTheDocument();fireEvent.click(screen.getByRole("button",{name:"Create appointment"}));expect(screen.getByRole("form",{name:"Create operational appointment"})).toBeInTheDocument();});
  it("limits physiotherapist actions to assigned lifecycle controls",async()=>{vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify([appointment]),{status:200}));wrap(<AssignedAppointments/>);expect(await screen.findByText("Asha Sharma")).toBeInTheDocument();expect(screen.getByRole("button",{name:"Start"})).toBeInTheDocument();expect(screen.getByRole("button",{name:"No show"})).toBeInTheDocument();});
  it("shows customers a safe appointment summary",async()=>{vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify([appointment]),{status:200}));wrap(<CustomerAppointments/>);expect(await screen.findByText("Physiotherapy")).toBeInTheDocument();expect(screen.getByText(/Dr Physio User/)).toBeInTheDocument();expect(screen.queryByText(/mobile/i)).not.toBeInTheDocument();});
});
