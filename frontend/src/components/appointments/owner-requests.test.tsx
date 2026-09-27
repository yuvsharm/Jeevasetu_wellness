import {QueryClient,QueryClientProvider} from "@tanstack/react-query";
import {fireEvent,render,screen,waitFor} from "@testing-library/react";
import {afterEach,beforeEach,describe,expect,it,vi} from "vitest";
import {OwnerRequests} from "./owner-requests";

const request={id:"request-1",therapy:"t1",therapy_name:"Kati Basti",requested_therapy_names:["Kati Basti"],requested_duration_minutes:45,patient_name:"Meera Relative",mobile_number:"9876543210",preferred_date:"2026-09-15",preferred_time:"10:00:00",address:"163 C Block",landmark:"Near park",city:"Meerut",region:"Uttar Pradesh",pin_code:"250004",status:"PENDING",created_at:"2026-09-07T08:00:00Z",final_amount:"1900.00",commercial_snapshot:{offer_title:"",package_name:"",final_amount:"1900.00"}};
afterEach(()=>window.history.replaceState(null,"","/"));
function setup(){let state={...request};const calls:Array<Record<string,unknown>>=[];const fetchMock=vi.spyOn(global,"fetch").mockImplementation(async(input,init)=>{const url=String(input);if(url.includes("eligible-physiotherapists"))return new Response(JSON.stringify([{id:"p0",full_name:"Busy Therapist",qualification:"BPT",age:30,experience_years:3,experience_months:0,specialization:"",expertise:["Kati Basti"],rating:null,review_count:0,has_photo:false,eligible:false,eligibility_reason:"Overlapping appointment"},{id:"p1",full_name:"Krishna",qualification:"MPT",age:31,experience_years:2,experience_months:0,specialization:"Orthopaedic",expertise:["Kati Basti"],rating:4.5,review_count:2,has_photo:false,eligible:true,eligibility_reason:"Available for this requested time"}]),{status:200});if(url.endsWith("/decision")&&init?.method==="POST"){const body=JSON.parse(String(init.body));calls.push(body);if(body.action==="ACCEPT"){state={...state,status:"APPROVED"};return new Response(JSON.stringify(state),{status:200})}return new Response(JSON.stringify({...state,appointment:{id:"a1",physiotherapist_name:"Krishna",scheduled_start:"2026-09-15T10:00:00+05:30"}}),{status:200})}return new Response(JSON.stringify({count:1,next:null,previous:null,results:[state]}),{status:200})});const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});return {calls,fetchMock,...render(<QueryClientProvider client={client}><OwnerRequests/></QueryClientProvider>)};}
describe("owner request assignment",()=>{beforeEach(()=>{vi.restoreAllMocks();window.history.replaceState(null,"","/")});it("accepts first, filters the exact slot, and then confirms one canonical appointment",async()=>{const {calls}=setup();fireEvent.click(await screen.findByRole("button",{name:"Accept Request"}));await waitFor(()=>expect(calls[0]).toMatchObject({action:"ACCEPT"}));fireEvent.click(await screen.findByRole("button",{name:"Assign Therapist / Book Slot"}));const radios=await screen.findAllByRole("radio");expect(radios[0]).toBeDisabled();expect(screen.getByText("Overlapping appointment")).toBeInTheDocument();fireEvent.click(radios[1]);fireEvent.click(screen.getByRole("button",{name:"Confirm Appointment"}));await waitFor(()=>expect(calls[1]).toMatchObject({action:"ASSIGN",physiotherapist:"p1"}));expect(await screen.findByText(/Appointment confirmed with Krishna/)).toBeInTheDocument()});it("requires a customer-safe rejection reason",async()=>{setup();fireEvent.click(await screen.findByText("Reject"));expect(screen.getByRole("button",{name:"Confirm rejection"})).toBeDisabled();fireEvent.change(screen.getByLabelText("Reason category"),{target:{value:"SCHEDULING_CONFLICT"}});fireEvent.change(screen.getByLabelText("Customer-safe reason"),{target:{value:"The slot is unavailable."}});expect(screen.getByRole("button",{name:"Confirm rejection"})).toBeEnabled()})});

it("opens and highlights the exact payment request from its notification deep link",async()=>{
  window.history.replaceState(null,"","/owner?request=request-1#appointment-requests");
  const pending={...request,appointment:{id:"a-verify",status:"PENDING_ASSIGNMENT",assignment_status:"UNASSIGNED",physiotherapist_name:null,scheduled_start:"2026-09-15T10:00:00+05:30",scheduled_end:"2026-09-15T10:45:00+05:30",duration_minutes:45,payment_status:"VERIFICATION_PENDING",payment_amount_due:"1900.00"}};
  vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify({count:1,next:null,previous:null,results:[pending]})));
  render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><OwnerRequests/></QueryClientProvider>);
  expect(await screen.findByRole("dialog",{name:"Verify Payment"})).toBeInTheDocument();
  expect(document.getElementById("appointment-request-request-1")).toHaveClass("ring-4");
});

it("shows the canonical recipient, registered contact, and responsive full service address without an internal UUID",async()=>{setup();expect(await screen.findByRole("heading",{name:"Meera Relative"})).toBeInTheDocument();expect(screen.getByText("9876543210")).toBeInTheDocument();expect(screen.getByText("163 C Block, Near park, Meerut, Uttar Pradesh, 250004")).toBeInTheDocument();expect(screen.getByText("Service address").parentElement).toHaveClass("sm:col-span-2");expect(screen.queryByText("request-1")).not.toBeInTheDocument()});

it("shows canonical booked history instead of assignment controls",async()=>{vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify({count:1,next:null,previous:null,results:[{...request,status:"APPROVED",appointment:{id:"a1",status:"COMPLETED",physiotherapist_name:"Krishna",scheduled_start:"2026-09-15T10:00:00+05:30",duration_minutes:45,payment_status:"PAID",payment_amount_due:"1900.00"}}]}),{status:200}));render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><OwnerRequests/></QueryClientProvider>);expect(await screen.findByText("SESSION COMPLETED")).toBeInTheDocument();expect(screen.getByText(/Assigned therapist: Krishna/)).toBeInTheDocument();expect(screen.queryByRole("button",{name:"Assign Therapist / Book Slot"})).not.toBeInTheDocument();expect(screen.getByText(/Payment: Payment Confirmed · ₹1900.00/)).toBeInTheDocument()});

it("returns a declined prepaid assignment to the Owner reassignment queue",async()=>{vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify({count:1,next:null,previous:null,results:[{...request,status:"APPROVED",appointment:{id:"a-declined",status:"SCHEDULED",assignment_status:"REJECTED",physiotherapist_name:"Prior Therapist",scheduled_start:"2026-09-15T10:00:00+05:30",scheduled_end:"2026-09-15T10:45:00+05:30",duration_minutes:45,payment_status:"PAID",payment_amount_due:"1900.00"}}]})));render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><OwnerRequests/></QueryClientProvider>);expect(await screen.findByText("Assigned therapist: Assignment pending")).toBeInTheDocument();expect(screen.getByText("Assignment status: Assignment pending · Previous therapist declined")).toBeInTheDocument();expect(screen.getByRole("button",{name:"Assign Therapist"})).toBeInTheDocument()});

it("assigns a paid prepaid booking from its exact-slot availability panel",async()=>{
  let appointment={id:"a-paid",status:"SCHEDULED",assignment_status:"UNASSIGNED",physiotherapist_name:null as string|null,scheduled_start:"2026-09-15T10:00:00+05:30",scheduled_end:"2026-09-15T10:45:00+05:30",duration_minutes:45,payment_status:"PAID",payment_amount_due:"1900.00",updated_at:"2026-09-07T08:00:00Z"};
  const calls:Array<Record<string,unknown>>=[];
  vi.spyOn(global,"fetch").mockImplementation(async(input,init)=>{
    const url=String(input);
    if(url.includes("eligible-physiotherapists"))return new Response(JSON.stringify([
      {id:"p-busy",full_name:"Busy Therapist",qualification:"BPT",age:30,experience_years:3,experience_months:0,specialization:"",expertise:["Kati Basti"],rating:null,review_count:0,has_photo:false,eligible:false,eligibility_reason:"The Physiotherapist already has an overlapping appointment."},
      {id:"p-free",full_name:"Krishna",qualification:"MPT",age:31,experience_years:2,experience_months:0,specialization:"Orthopaedic",expertise:["Kati Basti"],rating:4.5,review_count:2,has_photo:false,eligible:true,eligibility_reason:"Available for this requested time"},
    ]));
    if(url==="/api/schedule/a-paid/assign"&&init?.method==="POST"){
      calls.push(JSON.parse(String(init.body)));
      appointment={...appointment,assignment_status:"PENDING",physiotherapist_name:"Krishna",updated_at:"2026-09-07T08:01:00Z"};
      return new Response(JSON.stringify(appointment));
    }
    return new Response(JSON.stringify({count:1,next:null,previous:null,results:[{...request,status:"APPROVED",appointment}]}));
  });
  render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})}><OwnerRequests/></QueryClientProvider>);
  fireEvent.click(await screen.findByRole("button",{name:"Assign Therapist"}));
  expect(await screen.findByRole("dialog",{name:"Assign therapist"})).toHaveTextContent("45 minutes");
  expect(await screen.findByText("Conflict")).toBeInTheDocument();
  const radios=await screen.findAllByRole("radio");
  expect(radios[0]).toBeDisabled();
  expect(screen.getByText("Available")).toBeInTheDocument();
  fireEvent.click(radios[1]);
  fireEvent.click(screen.getByRole("button",{name:"Confirm Assignment"}));
  await waitFor(()=>expect(calls[0]).toMatchObject({physiotherapist:"p-free",expected_updated_at:"2026-09-07T08:00:00Z"}));
  expect(await screen.findByText(/Therapist assignment sent to Krishna/)).toBeInTheDocument();
  await waitFor(()=>expect(screen.getByText("Assigned therapist: Krishna")).toBeInTheDocument());
  expect(screen.getByText("Assignment status: PENDING")).toBeInTheDocument();
  expect(screen.queryByRole("button",{name:"Assign Therapist"})).not.toBeInTheDocument();
});

it("verifies a submitted payment before exposing therapist assignment",async()=>{
  let appointment={id:"a-verify",status:"PENDING_ASSIGNMENT",assignment_status:"UNASSIGNED",physiotherapist_name:null as string|null,scheduled_start:"2026-09-15T10:00:00+05:30",scheduled_end:"2026-09-15T10:45:00+05:30",duration_minutes:45,payment_status:"VERIFICATION_PENDING",payment_amount_due:"1900.00",updated_at:"2026-09-07T08:00:00Z"};
  let requestStatus="PENDING";
  const calls:Array<{url:string;body:Record<string,unknown>}>=[];
  const fetchMock=vi.spyOn(global,"fetch").mockImplementation(async(input,init)=>{
    const url=String(input);
    if(url==="/api/schedule/a-verify/payment"&&init?.method==="POST"){
      calls.push({url,body:JSON.parse(String(init.body))});
      requestStatus="APPROVED";
      appointment={...appointment,status:"SCHEDULED",payment_status:"PAID",updated_at:"2026-09-07T08:01:00Z"};
      return new Response(JSON.stringify({status:"PAID"}));
    }
    if(url.includes("eligible-physiotherapists"))return new Response(JSON.stringify([{id:"p-free",full_name:"Krishna",qualification:"MPT",age:31,experience_years:2,experience_months:0,specialization:"Orthopaedic",expertise:["Kati Basti"],rating:4.5,review_count:2,has_photo:false,eligible:true,eligibility_reason:"Available for this requested time"}]));
    if(url==="/api/schedule/a-verify/assign"&&init?.method==="POST"){
      calls.push({url,body:JSON.parse(String(init.body))});
      appointment={...appointment,assignment_status:"PENDING",physiotherapist_name:"Krishna",updated_at:"2026-09-07T08:02:00Z"};
      return new Response(JSON.stringify(appointment));
    }
    return new Response(JSON.stringify({count:1,next:null,previous:null,results:[{...request,status:requestStatus,appointment}]}));
  });
  render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})}><OwnerRequests/></QueryClientProvider>);

  expect(await screen.findByText("Payment verification required",{selector:"strong"})).toBeInTheDocument();
  expect(screen.queryByText("VERIFICATION_PENDING")).not.toBeInTheDocument();
  expect(screen.queryByRole("button",{name:"Accept Request"})).not.toBeInTheDocument();
  expect(screen.queryByRole("button",{name:"Assign Therapist"})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"Verify Payment"}));

  const dialog=screen.getByRole("dialog",{name:"Verify Payment"});
  expect(dialog).toHaveTextContent("Meera Relative");
  expect(dialog).toHaveTextContent("9876543210");
  expect(dialog).toHaveTextContent("Kati Basti");
  expect(dialog).toHaveTextContent("₹1900.00");
  expect(dialog).toHaveTextContent("163 C Block, Near park, Meerut, Uttar Pradesh, 250004");
  expect(dialog).toHaveTextContent("Confirm only after verifying that payment has been received.");
  fireEvent.click(screen.getByRole("button",{name:"Confirm Payment Received"}));

  await waitFor(()=>expect(calls[0]).toEqual({url:"/api/schedule/a-verify/payment",body:{status:"PAID",reference:"",note:"Verified from Appointment Requests."}}));
  expect(await screen.findByText("Payment Confirmed",{selector:"strong"})).toBeInTheDocument();
  expect(screen.getByRole("button",{name:"Assign Therapist"})).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"Assign Therapist"}));
  fireEvent.click(await screen.findByRole("radio"));
  fireEvent.click(screen.getByRole("button",{name:"Confirm Assignment"}));
  await waitFor(()=>expect(calls[1]).toMatchObject({url:"/api/schedule/a-verify/assign",body:{physiotherapist:"p-free",expected_updated_at:"2026-09-07T08:01:00Z"}}));
  expect(await screen.findByText(/Therapist assignment sent to Krishna/)).toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([input,init])=>String(input)==="/api/appointment-requests"&&init?.method==="POST")).toBe(false);
});
