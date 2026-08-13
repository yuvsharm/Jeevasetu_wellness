import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EnrollmentForm } from "@/components/practitioners/enrollment-form";
import { OpenToWorkControl } from "@/components/practitioners/open-to-work";
import { PublicPractitionerDirectory } from "@/components/practitioners/public-directory";

const draft = { id:"application-1", status:"DRAFT", category:"PHYSIOTHERAPIST", full_legal_name:"Dr Saved Applicant", date_of_birth:null, gender:"PREFER_NOT_TO_SAY", mobile_number:"", alternate_mobile:"", email:"", current_address:"", city:"Meerut", state:"Uttar Pradesh", pin_code:"", highest_qualification:"BPT", specialization:"", college_institute:"", awarding_body:"", passing_year:null, registration_number:"", registration_authority:"", registration_expiry:null, experience_years:0, experience_months:0, recent_organization:"", previous_experience:"", has_home_service_experience:false, bio:"", languages:["Hindi"], clinic:null, availability_notes:"", last_completed_step:0, has_profile_photo:false, correction_reason:"", rejection_reason:"", documents:[], competencies:[] };
function wrap(ui:React.ReactNode){return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}>{ui}</QueryClientProvider>)}

describe("practitioner enrollment",()=>{
  beforeEach(()=>vi.restoreAllMocks());

  it("restores a saved server draft and shows all six responsive steps",async()=>{
    vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify([draft]),{status:200}));
    wrap(<EnrollmentForm/>);
    expect(await screen.findByDisplayValue("Dr Saved Applicant")).toBeInTheDocument();
    expect(screen.getByLabelText("Application progress")).toBeInTheDocument();
    expect(screen.getByText("Step 1 of 6")).toBeInTheDocument();
    expect(screen.getByRole("button",{name:"Review"})).toBeInTheDocument();
  });

  it("renders a rejected application as a terminal status without creating a new draft",async()=>{
    const rejected={...draft,status:"REJECTED",last_completed_step:3,rejection_reason:"Registration could not be verified."};
    const fetchMock=vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify([rejected]),{status:200}));
    wrap(<EnrollmentForm/>);
    expect(await screen.findByText("Application rejected")).toBeInTheDocument();
    expect(screen.getByText(/Registration could not be verified/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Application progress")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([,init])=>init?.method==="POST")).toBe(false);
  });
  it("creates an early server draft and persists step changes",async()=>{
    const calls: Array<[string,RequestInit|undefined]> = [];
    vi.spyOn(global,"fetch").mockImplementation(async(input,init)=>{
      const url=String(input);calls.push([url,init]);
      if(url==="/api/practitioners/me"&&!init?.method)return new Response("[]",{status:200});
      if(url==="/api/practitioners/me"&&init?.method==="POST")return new Response(JSON.stringify({...draft,full_legal_name:""}),{status:200});
      return new Response(JSON.stringify({...draft,last_completed_step:1}),{status:200});
    });
    wrap(<EnrollmentForm/>);
    await userEvent.type(await screen.findByLabelText(/Full legal name/),"Dr Autosaved");
    await userEvent.click(screen.getByRole("button",{name:/save and continue/i}));
    await waitFor(()=>expect(calls.some(([,init])=>init?.method==="PATCH")).toBe(true));
  });

  it("keeps local form state when autosave fails",async()=>{
    const fetchMock=vi.spyOn(global,"fetch").mockImplementation(async(_input,init)=>init?.method==="PATCH"?new Response(JSON.stringify({detail:"invalid"}),{status:400}):new Response(JSON.stringify([draft]),{status:200}));
    wrap(<EnrollmentForm/>);
    const name=await screen.findByLabelText(/Full legal name/);
    await userEvent.clear(name);await userEvent.type(name,"Dr Still Here");
    await userEvent.click(screen.getByRole("button",{name:/save and continue/i}));
    await userEvent.click(screen.getByRole("button",{name:/back/i}));
    expect(screen.getByDisplayValue("Dr Still Here")).toBeInTheDocument();
    expect(await screen.findByRole("button",{name:/save failed/i})).toBeInTheDocument();
    const failedPatchCount=fetchMock.mock.calls.filter(([,init])=>init?.method==="PATCH").length;
    await new Promise(resolve=>setTimeout(resolve,1200));
    expect(fetchMock.mock.calls.filter(([,init])=>init?.method==="PATCH")).toHaveLength(failedPatchCount);
  });

  it("retries a transient autosave failure with a bounded backoff",async()=>{
    let patches=0;
    vi.spyOn(global,"fetch").mockImplementation(async(_input,init)=>{
      if(init?.method==="PATCH"){patches+=1;return patches<3?new Response(JSON.stringify({detail:"temporary"}),{status:503}):new Response(JSON.stringify({...draft,full_legal_name:"Dr Recovered"}),{status:200})}
      return new Response(JSON.stringify([draft]),{status:200});
    });
    wrap(<EnrollmentForm/>);
    const name=await screen.findByLabelText(/Full legal name/);
    await userEvent.clear(name);await userEvent.type(name,"Dr Recovered");
    await userEvent.click(screen.getByRole("button",{name:/save and continue/i}));
    expect(await screen.findByText(/Saved just now/i,{}, {timeout:6000})).toBeInTheDocument();
    expect(patches).toBe(3);
  });

  it("uploads a valid image and maps backend failures separately from invalid files",async()=>{
    Object.defineProperty(URL,"createObjectURL",{configurable:true,value:vi.fn(()=>"blob:profile-photo")});
    let uploadStatus=200;
    vi.spyOn(global,"fetch").mockImplementation(async(_input,init)=>{
      if(init?.method==="POST")return new Response(uploadStatus===200?JSON.stringify({detail:"ok"}):JSON.stringify({detail:"server error"}),{status:uploadStatus});
      return new Response(JSON.stringify([draft]),{status:200});
    });
    wrap(<EnrollmentForm/>);
    const input=await screen.findByLabelText(/Upload photo/i);
    await userEvent.upload(input,new File([new Uint8Array(16*1024)],"profile.jpg",{type:"image/jpeg"}));
    expect(await screen.findByText(/Uploaded successfully/i)).toBeInTheDocument();

    uploadStatus=500;
    await userEvent.upload(screen.getByLabelText(/Replace/i),new File([new Uint8Array(16*1024)],"replacement.jpg",{type:"image/jpeg"}));
    expect(await screen.findByText("We couldn't upload the photo right now. Please try again.")).toBeInTheDocument();
    expect(screen.queryByText(/choose a valid JPG/i)).not.toBeInTheDocument();
  });

  it("uses the authenticated filename control without an eye icon",async()=>{
    const withDocument={...draft,last_completed_step:4,documents:[{id:"document-1",kind:"GOVERNMENT_ID",original_name:"identity-proof.pdf",content_type:"application/pdf",size_bytes:438272,verification_status:"PENDING",created_at:"2026-08-10T10:00:00Z"}]};
    vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify([withDocument]),{status:200}));
    wrap(<EnrollmentForm/>);
    expect((await screen.findAllByText("identity-proof.pdf")).length).toBeGreaterThan(0);
    expect(screen.getByText("428 KB")).toBeInTheDocument();
    expect(screen.getByRole("button",{name:"identity-proof.pdf"})).toBeInTheDocument();
    expect(screen.queryByRole("button",{name:/View Government identity proof/i})).not.toBeInTheDocument();
    expect(screen.getByText("Change PDF")).toBeInTheDocument();
    expect(screen.getByRole("button",{name:"Remove Government identity proof"})).toBeInTheDocument();
  });

  it("opens and deletes the exact document ID through authenticated routes",async()=>{
    const withDocument={...draft,last_completed_step:4,documents:[{id:"government-id-1",kind:"GOVERNMENT_ID",original_name:"identity-proof.pdf",content_type:"application/pdf",size_bytes:438272,verification_status:"PENDING",created_at:"2026-08-10T10:00:00Z"}]};
    const fetchMock=vi.spyOn(global,"fetch").mockImplementation(async(input,init)=>{
      const url=String(input);
      if(url==="/api/practitioners/documents/government-id-1"&&init?.method==="DELETE")return new Response(null,{status:204});
      if(url==="/api/practitioners/documents/government-id-1")return new Response(new Blob(["%PDF-1.4 government-id"],{type:"application/pdf"}),{status:200,headers:{"Content-Type":"application/pdf"}});
      return new Response(JSON.stringify([withDocument]),{status:200});
    });
    Object.defineProperty(URL,"createObjectURL",{configurable:true,value:vi.fn(()=>"blob:government-id")});
    Object.defineProperty(URL,"revokeObjectURL",{configurable:true,value:vi.fn()});
    HTMLDialogElement.prototype.showModal=vi.fn();
    vi.spyOn(window,"confirm").mockReturnValue(true);
    wrap(<EnrollmentForm/>);
    await userEvent.click(await screen.findByRole("button",{name:"identity-proof.pdf"}));
    expect(fetchMock).toHaveBeenCalledWith("/api/practitioners/documents/government-id-1",{credentials:"same-origin"});
    await userEvent.click(screen.getByRole("button",{name:"Remove Government identity proof"}));
    await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith("/api/practitioners/documents/government-id-1",{method:"DELETE"}));
    expect(await screen.findByText("Document removed.")).toBeInTheDocument();
  });

  it("renders only safe verified directory information",async()=>{vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify([{id:"1",display_name:"Dr Asha Sharma",category:"PHYSIOTHERAPIST",highest_qualification:"MPT",qualification_specialization:"Orthopaedic",experience_years:9,languages:["Hindi"],bio:"Home service specialist",service_area:"Meerut",verified_services:["Physiotherapy"],photo_url:""}]),{status:200}));wrap(<PublicPractitionerDirectory/>);expect(await screen.findByText("Dr Asha Sharma")).toBeInTheDocument();expect(screen.getByText("JeevaSetu Verified")).toBeInTheDocument();expect(screen.queryByText(/email|mobile|government/i)).not.toBeInTheDocument();});
  it("provides an explicit Open to Work switch",async()=>{vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify({is_open_to_work:true}),{status:200}));wrap(<OpenToWorkControl/>);const control=screen.getByRole("switch");expect(control).toHaveAttribute("aria-checked","false");await userEvent.click(control);expect(await screen.findByRole("switch")).toHaveAttribute("aria-checked","true");});
});
