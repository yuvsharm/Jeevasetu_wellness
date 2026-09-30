import {QueryClient,QueryClientProvider} from "@tanstack/react-query";
import {fireEvent,render,screen,waitFor} from "@testing-library/react";
import {beforeEach,expect,it,vi} from "vitest";
import {DobEditor} from "./dob-editor";
import {DobField,DobReview} from "./dob-field";
import {PractitionerCard,PractitionerCarousel} from "./public-directory";
import type {PublicPractitioner} from "@/lib/practitioners/contracts";
vi.mock("next/navigation",()=>({useRouter:()=>({replace:vi.fn()}),useSearchParams:()=>new URLSearchParams()}));
const item:PublicPractitioner={id:"1",display_name:"Test Therapist",age:36,category:"PHYSIOTHERAPIST",highest_qualification:"MPT",qualification_specialization:"",experience_years:4,experience_months:6,gender:"Female",languages:[],bio:"",service_area:"Meerut",verified_services:["Abhyang","Basti","Nasya","Potli","Other"],photo_url:"/api/practitioners/public/1/photo",average_rating:4.8,review_count:23};
function wrap(child:React.ReactNode){const client=new QueryClient({defaultOptions:{queries:{retry:false}}});return render(<QueryClientProvider client={client}>{child}</QueryClientProvider>)}
beforeEach(()=>vi.restoreAllMocks());
it("shares a required private date picker and uses server-derived age in review",async()=>{
 vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify({age:36})));
 render(<><DobField value="1990-08-15" onChange={vi.fn()}/><DobReview value="1990-08-15"/></>);
 expect(screen.getByLabelText("Date of Birth *")).toHaveAttribute("type","date");expect(screen.getByLabelText("Date of Birth *")).toBeRequired();
 expect(screen.getByText("Date of Birth: 15 Aug 1990")).toBeInTheDocument();expect(await screen.findByText("Age: 36 years")).toBeInTheDocument();
});
it("saves authorized DOB independently of mobile verification",async()=>{
 const fetchMock=vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify({age:35})));
 wrap(<DobEditor dob={null} age={null} url="/api/staff/profiles/1"/>);
 fireEvent.click(screen.getByRole("button",{name:"Edit Date of Birth"}));fireEvent.change(screen.getByLabelText("Date of Birth *"),{target:{value:"1991-08-15"}});fireEvent.click(screen.getByRole("button",{name:"Save Date of Birth"}));
 await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith("/api/staff/profiles/1",expect.objectContaining({method:"PATCH",body:'{"date_of_birth":"1991-08-15"}'})));expect(fetchMock).toHaveBeenCalledTimes(1);
});
it("renders safe compact public details, real rating and only three competencies",()=>{
 render(<PractitionerCard item={item} compact/>);expect(screen.getByText("Age: 36 years")).toBeInTheDocument();expect(screen.getByText("MPT")).toBeInTheDocument();expect(screen.getByText(/4 years 6 months/)).toBeInTheDocument();expect(screen.getByText("+2 more")).toBeInTheDocument();expect(screen.queryByText("Potli")).not.toBeInTheDocument();expect(screen.getByLabelText("4.8 out of 5 stars")).toBeInTheDocument();expect(screen.getByText(/23 reviews/)).toBeInTheDocument();expect(screen.getByText("Available with NuriPain Ease")).toBeInTheDocument();expect(screen.queryByText(/date of birth/i)).not.toBeInTheDocument();
 fireEvent.error(screen.getByRole("img"));expect(screen.getByText("TT")).toBeInTheDocument();
});
it("does not fabricate missing age, photo or rating",()=>{render(<PractitionerCard item={{...item,age:null,photo_url:"",average_rating:null,review_count:0}}/>);expect(screen.getByText("TT")).toBeInTheDocument();expect(screen.getByText("No ratings yet")).toBeInTheDocument();expect(screen.queryByText(/Age:/)).not.toBeInTheDocument();expect(screen.queryByLabelText(/out of 5 stars/)).not.toBeInTheDocument();});
it("provides a horizontal snap track and working navigation",async()=>{
 vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify([item,{...item,id:"2",display_name:"Second Therapist"}])));
 wrap(<PractitionerCarousel/>);const track=await screen.findByLabelText("Verified practitioner carousel");
 expect(track).toHaveClass("flex","overflow-x-auto","snap-x","max-w-full");
 Object.defineProperty(track,"clientWidth",{value:400});Object.defineProperty(track,"scrollWidth",{value:800});const scrollTo=vi.fn();track.scrollTo=scrollTo;
 fireEvent.click(screen.getByRole("button",{name:"Next practitioners"}));expect(scrollTo).toHaveBeenCalledWith({left:336,behavior:"smooth"});
});
