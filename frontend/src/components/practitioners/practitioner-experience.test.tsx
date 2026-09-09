import {QueryClient,QueryClientProvider} from "@tanstack/react-query";
import {fireEvent,render,screen,waitFor} from "@testing-library/react";
import {beforeEach,describe,expect,it,vi} from "vitest";

import {LearningCentre,LearningGuidePage} from "./learning-centre";
import {MyPractitionerProfile} from "./my-profile";

const profile={id:"staff-1",user_id:"user-1",staff_type:"PHYSIOTHERAPIST",full_name:"Asha Verma",first_name:"Asha",last_name:"Verma",email:"asha@example.com",mobile:"+919876543210",photo_url:"",profile_photo:"",gender:"FEMALE",age:36,date_of_birth:"1990-08-15",qualification:"MPT",registration_number:"",experience_years:4,experience_months:6,specialization_ids:["specialization-1"],specialization_names:["Orthopaedics"],therapy_competency_ids:["therapy-1"],verified_therapy_ids:["therapy-1"],verified_therapy_names:["Physiotherapy"],profile_source:"STAFF_CREATED",approved_weekly_rule_count:6,approval_status:"VERIFIED_APPROVED",activation_status:"ACCOUNT_ACTIVATED",is_publicly_visible:true,languages_known:["Hindi","English"],alternate_mobile:"",emergency_contact:"",current_address:"",city:"",pin_code:"",clinic:"clinic-1",clinic_name:"Meerut",service_area_ids:["area-1"],service_area_names:["Meerut"],availability:"AVAILABLE",is_online:false,joining_date:"2026-01-01",is_active:true,bio:"Home-care physiotherapist",documents:[],operating_days:[],upcoming_leave:[]};
const sections=["overview","indications","contraindications","patient_preparation","practitioner_preparation","equipment","procedure","positioning","duration","precautions","stop_criteria","aftercare","common_mistakes","documentation","key_takeaways"];
const guide={id:"guide-1",therapy:"therapy-1",therapy_name:"Physiotherapy",title_en:"Physiotherapy",title_hi:"फिजियोथेरेपी",content_en:Object.fromEntries(sections.map(k=>[k,`${k} English`])),content_hi:Object.fromEntries(sections.map(k=>[k,`${k} Hindi`])),published:true,version:2,updated_at:"2026-09-06T10:00:00Z",reviewed_at:"2026-09-06T10:00:00Z",learning_minutes:20,images:[{id:"image-1",url:"/api/learning/images/image-1",caption_en:"Position",caption_hi:"स्थिति",alt_text:"Approved positioning diagram",sort_order:0}],videos:[{id:"video-1",title:"Approved demonstration",youtube_url:"https://youtu.be/abcdefghijk",video_id:"abcdefghijk",language:"en",description:"Approved reference",sort_order:0,approved:true}],sections};
function wrap(ui:React.ReactNode){return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})}>{ui}</QueryClientProvider>)}

describe("therapist practitioner experience",()=>{
 beforeEach(()=>vi.restoreAllMocks());

 it("edits allowed profile fields and uploads a canonical photo as multipart",async()=>{
  const calls:Array<[string,RequestInit|undefined]>=[];
vi.spyOn(globalThis,"fetch").mockImplementation(async(input,init)=>{const url=String(input);calls.push([url,init]);if(url==="/api/staff/me")return new Response(JSON.stringify(profile));if(url.endsWith("/options"))return new Response(JSON.stringify({specializations:[{id:"specialization-1",name:"Orthopaedics"}],service_areas:[{id:"area-1",name:"Meerut"}],therapies:[{id:"therapy-1",name:"Physiotherapy"},{id:"therapy-2",name:"New Therapy"}]}));if(url.endsWith("/competencies")&&(!init?.method||init.method==="GET"))return new Response(JSON.stringify([{therapy_id:"therapy-1",therapy_name:"Physiotherapy",status:"SELECTED"},{therapy_id:"therapy-2",therapy_name:"New Therapy",status:"NOT_SELECTED"}]));if(url.endsWith("/credentials"))return new Response(JSON.stringify([]));if(url.includes("reviews/mine"))return new Response(JSON.stringify({average_rating:4.6,review_count:18,reviews:[]}));if(url.includes("open-to-work"))return new Response(JSON.stringify({is_open_to_work:true}));return new Response(JSON.stringify({detail:"ok"}));});
  wrap(<MyPractitionerProfile/>);
  expect(await screen.findByRole("heading",{name:"Asha Verma"})).toBeInTheDocument();
  expect(screen.getByLabelText("Asha Verma avatar")).toHaveTextContent("AV");
  expect((await screen.findAllByLabelText("4.6 out of 5 stars")).some(node=>node.classList.contains("text-amber-500"))).toBe(true);
  fireEvent.click(screen.getByRole("button",{name:"Edit Profile"}));
  expect(screen.getByText("✓ Physiotherapy")).toBeInTheDocument();
  expect(screen.queryByText("✓ Verified")).not.toBeInTheDocument();
  expect(screen.queryByText("Pending Verification")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"+ Add Therapy"}));
  fireEvent.click(screen.getByRole("checkbox",{name:"New Therapy"}));
  fireEvent.click(screen.getByRole("button",{name:"Add Selected Therapies"}));
  fireEvent.change(screen.getByLabelText("First name"),{target:{value:"Aashi"}});
  fireEvent.change(screen.getByLabelText("Experience months"),{target:{value:"8"}});
  fireEvent.click(screen.getByRole("button",{name:"Save Changes"}));
  await waitFor(()=>expect(calls.some(([url,init])=>url==="/api/staff/me"&&init?.method==="PATCH"&&String(init.body).includes('"first_name":"Aashi"')&&String(init.body).includes('"experience_months":8'))).toBe(true));
  await waitFor(()=>expect(calls.some(([url,init])=>url==="/api/staff/me/competencies"&&init?.method==="POST"&&String(init.body).includes('"therapy_id":"therapy-2"'))).toBe(true));
  const photo=new File(["photo"],"asha.png",{type:"image/png"});
  fireEvent.change(screen.getByLabelText("Upload New Photo"),{target:{files:[photo]}});
  await waitFor(()=>{const upload=calls.find(([url,init])=>url==="/api/staff/me/photo"&&init?.method==="POST");expect(upload?.[1]?.body).toBeInstanceOf(FormData);expect(new Headers(upload?.[1]?.headers).has("Content-Type")).toBe(false)});
 });

 it("shows approved learning cards and switches one guide between English and Hindi",async()=>{
  vi.spyOn(globalThis,"fetch").mockImplementation(async input=>new Response(JSON.stringify(String(input)==="/api/learning"?{guides:[guide],therapies:[{id:"therapy-1",name:"Physiotherapy"}],sections}:guide)));
  const first=wrap(<LearningCentre/>);expect(await screen.findByRole("heading",{name:"Physiotherapy"})).toBeInTheDocument();expect(screen.getByText("20 min · Version 2")).toBeInTheDocument();first.unmount();
  wrap(<LearningGuidePage id="guide-1"/>);expect(await screen.findByText("overview English")).toBeInTheDocument();expect(screen.getByRole("img",{name:"Approved positioning diagram"})).toBeInTheDocument();expect(screen.getByTitle("Approved demonstration")).toHaveAttribute("src","https://www.youtube-nocookie.com/embed/abcdefghijk");fireEvent.click(screen.getByRole("button",{name:"हिंदी"}));expect(screen.getByRole("heading",{name:"फिजियोथेरेपी"})).toBeInTheDocument();expect(screen.getByText("overview Hindi")).toBeInTheDocument();
 });

 it("lets the Owner create only an unpublished empty draft from an active therapy",async()=>{
  const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(async(input,init)=>new Response(JSON.stringify(init?.method==="POST"?{...guide,published:false}:{guides:[],therapies:[{id:"therapy-1",name:"Physiotherapy"}],sections})));
  wrap(<LearningCentre owner/>);fireEvent.click(await screen.findByRole("button",{name:"+ Physiotherapy"}));await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith("/api/learning",expect.objectContaining({method:"POST",body:JSON.stringify({therapy:"therapy-1",title_en:"Physiotherapy"})})));
 });

 it("requires clinical approval to publish and provides a separate unpublish action",async()=>{
  let current={...guide,published:false};
  const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(async(input,init)=>{if(init?.method==="PATCH"){const body=JSON.parse(String(init.body));current={...current,published:Boolean(body.published)};return new Response(JSON.stringify(current))}return new Response(JSON.stringify(current))});
  wrap(<LearningGuidePage id="guide-1" owner/>);
  expect(await screen.findByRole("button",{name:"Save Draft"})).toBeInTheDocument();
  expect(screen.getByRole("button",{name:"Publish Guide"})).toBeDisabled();
  fireEvent.click(screen.getByRole("button",{name:"Preview as Therapist"}));
  fireEvent.click(screen.getByRole("checkbox",{name:/Clinical Approval/}));
  fireEvent.click(screen.getByRole("button",{name:"Publish Guide"}));
  await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith("/api/learning/guide-1",expect.objectContaining({method:"PATCH",body:JSON.stringify({published:true,clinical_approval:true})})));
 expect(await screen.findByText(/Guide published successfully/)).toBeInTheDocument();
 fireEvent.click(await screen.findByRole("button",{name:"Unpublish Guide"}));
 await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith("/api/learning/guide-1",expect.objectContaining({method:"PATCH",body:JSON.stringify({published:false,clinical_approval:false})})));
 expect(await screen.findByText(/Guide unpublished successfully/)).toBeInTheDocument();
});
});
