import {QueryClient,QueryClientProvider} from "@tanstack/react-query";
import {fireEvent,render,screen,within,waitFor} from "@testing-library/react";
import {beforeEach,describe,expect,it,vi} from "vitest";
import {TherapistAvailabilityPage} from "./therapist-availability-page";

const profile={id:"staff-1",user_id:"user-1",staff_type:"PHYSIOTHERAPIST",full_name:"Asha Verma",email:"",mobile:"",profile_photo:"",gender:"FEMALE",date_of_birth:"",qualification:"MPT",registration_number:"",experience_years:4,experience_months:6,specialization_ids:[],specialization_names:[],therapy_competency_ids:[],verified_therapy_ids:[],verified_therapy_names:[],profile_source:"PRACTITIONER_APPLICATION",approved_weekly_rule_count:1,approval_status:"VERIFIED_APPROVED",activation_status:"ACCOUNT_ACTIVATED",is_publicly_visible:true,languages_known:[],alternate_mobile:"",emergency_contact:"",current_address:"",city:"",pin_code:"",clinic:"clinic-1",clinic_name:"Meerut",service_area_ids:[],availability:"AVAILABLE",is_online:true,joining_date:"2026-01-01",is_active:true,bio:"",documents:[]};
function wrap(){return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><TherapistAvailabilityPage staffId="staff-1"/></QueryClientProvider>)}

describe("dedicated therapist availability",()=>{
 beforeEach(()=>{vi.restoreAllMocks();vi.spyOn(global,"fetch").mockImplementation(async input=>{const url=String(input);if(url==="/api/staff/profiles/staff-1")return new Response(JSON.stringify(profile),{status:200});if(url.includes("/api/availability/rules"))return new Response(JSON.stringify({count:1,next:null,previous:null,results:[{id:"rule-1",physiotherapist:"staff-1",physiotherapist_name:"Asha Verma",clinic:"clinic-1",weekday:0,starts_at:"10:00:00",ends_at:"19:00:00",effective_from:"2026-01-01",effective_until:null,approval_status:"APPROVED",is_active:true,review_reason:"",created_at:""}]}),{status:200});return new Response(JSON.stringify({count:0,next:null,previous:null,results:[]}),{status:200})})});
 it("loads the routed therapist in a compact weekly table without slot discovery",async()=>{wrap();expect(await screen.findByRole("heading",{name:"Asha Verma"})).toBeInTheDocument();expect(screen.getByRole("table")).toBeInTheDocument();expect(screen.getByText("10:00 am – 7:00 pm")).toBeInTheDocument();expect(screen.getByText("Sunday").closest("tr")).toHaveTextContent("Off");expect(screen.queryByText("Find 15-minute slots")).not.toBeInTheDocument();expect(screen.queryByLabelText("Practitioner to manage")).not.toBeInTheDocument()});
 it("keeps the leave form collapsed until Add Leave",async()=>{wrap();await screen.findByRole("heading",{name:"Asha Verma"});expect(screen.queryByRole("form",{name:"Add temporary leave"})).not.toBeInTheDocument();fireEvent.click(screen.getByRole("button",{name:"+ Add Leave"}));expect(screen.getByRole("form",{name:"Add temporary leave"})).toBeInTheDocument()});

 it("lets the Owner add a current therapy without verification",async()=>{
  const calls:Array<[string,RequestInit|undefined]>=[];
  vi.spyOn(global,"fetch").mockImplementation(async(input,init)=>{const url=String(input);calls.push([url,init]);if(url==="/api/staff/profiles/staff-1")return new Response(JSON.stringify(profile));if(url==="/api/commercial/public")return new Response(JSON.stringify({therapies:[{id:"therapy-1",name:"Abhyang",is_active:true,is_offer_free_addon:false}]}));return new Response(JSON.stringify({count:0,next:null,previous:null,results:[]}))});
  wrap();await screen.findByRole("heading",{name:"Therapies I Can Perform"});
  fireEvent.click(screen.getByRole("button",{name:"+ Add Therapy"}));
  fireEvent.click(await screen.findByRole("checkbox",{name:"Abhyang"}));
  fireEvent.click(screen.getByRole("button",{name:"Add Selected Therapies"}));
  await waitFor(()=>expect(calls.some(([url,init])=>url==="/api/staff/profiles/staff-1/competencies"&&init?.method==="POST"&&String(init.body).includes('"therapy_id":"therapy-1"'))).toBe(true));
  expect(screen.queryByText(/verification/i)).not.toBeInTheDocument();
 });

 it("attaches one editor to the selected weekday and offers working hours for Off days",async()=>{
 wrap();await screen.findByRole("heading",{name:"Asha Verma"});
 fireEvent.click(within(screen.getByText("Monday").closest("tr")!).getByRole("button",{name:"Edit"}));
 const monday=screen.getByRole("form",{name:"Edit Monday"});
 expect(screen.getByText("Monday").closest("tr")!.nextElementSibling).toContainElement(monday);
 fireEvent.click(within(screen.getByText("Tuesday").closest("tr")!).getByRole("button",{name:"Set Working Hours"}));
 expect(screen.queryByRole("form",{name:"Edit Monday"})).not.toBeInTheDocument();
 expect(screen.getByText("Tuesday").closest("tr")!.nextElementSibling).toContainElement(screen.getByRole("form",{name:"Edit Tuesday"}));
 fireEvent.click(screen.getByRole("button",{name:"Cancel"}));expect(screen.queryByRole("form")).not.toBeInTheDocument();
 });
 it("submits date-only leave without browser timezone conversion",async()=>{
 wrap();await screen.findByRole("heading",{name:"Asha Verma"});fireEvent.click(screen.getByRole("button",{name:"+ Add Leave"}));
 expect(screen.getByLabelText("From Date")).toHaveAttribute("type","date");expect(screen.getByLabelText("To Date")).toHaveAttribute("type","date");
 fireEvent.change(screen.getByLabelText("From Date"),{target:{value:"2026-09-15"}});fireEvent.change(screen.getByLabelText("To Date"),{target:{value:"2026-09-16"}});
 fireEvent.click(screen.getByRole("button",{name:"Save Leave"}));await waitFor(()=>expect(fetch).toHaveBeenCalledWith("/api/availability/exceptions",expect.objectContaining({method:"POST",body:expect.stringContaining('"from_date":"2026-09-15","to_date":"2026-09-16"')})));
 });

 it("sets a day Off and restores it only after saving working hours",async()=>{
 let active=true;
 vi.spyOn(global,"fetch").mockImplementation(async(input,init)=>{
 const url=String(input);
 if(url==="/api/staff/profiles/staff-1")return new Response(JSON.stringify(profile));
 if(url.endsWith("/deactivate")){active=false;return new Response(JSON.stringify({}));}
 if(url.includes("/api/availability/rules")){
 if(init?.method==="POST")active=true;
 return new Response(JSON.stringify({results:active?[{id:"rule-1",weekday:0,starts_at:"10:00",ends_at:"19:00",approval_status:"APPROVED",is_active:true}]:[],next:null}));}
 return new Response(JSON.stringify({results:[],next:null}));});
 wrap();await screen.findByText("10:00 am – 7:00 pm");
 fireEvent.click(screen.getByRole("button",{name:"Set Off"}));
 await waitFor(()=>expect(within(screen.getByText("Monday").closest("tr")!).getByRole("button",{name:"Set Working Hours"})).toBeInTheDocument());
 fireEvent.click(within(screen.getByText("Monday").closest("tr")!).getByRole("button",{name:"Set Working Hours"}));expect(active).toBe(false);
 fireEvent.click(screen.getByRole("button",{name:"Save Monday"}));await screen.findByText("10:00 am – 7:00 pm");expect(active).toBe(true);
 });
 it("shows a clean closed Monday message and disables saving",async()=>{
 vi.spyOn(global,"fetch").mockImplementation(async input=>new Response(JSON.stringify(String(input)==="/api/staff/profiles/staff-1"?{...profile,operating_days:[{weekday:0,is_open:false,opens_at:null,closes_at:null}]}:{results:[],next:null})));
 wrap();await screen.findByRole("heading",{name:"Asha Verma"});fireEvent.click(within(screen.getByText("Monday").closest("tr")!).getByRole("button",{name:"Set Working Hours"}));
 expect(screen.getByText("Clinic is closed on Monday.")).toBeInTheDocument();expect(screen.getByRole("button",{name:"Save Monday"})).toBeDisabled();
 });
});
