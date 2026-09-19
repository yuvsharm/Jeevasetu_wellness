import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CustomerRatingPanel } from "@/components/appointments/customer-rating";
import { PublicReviews, ReviewModerationPanel } from "@/components/appointments/review-panels";

function renderQuery(ui:React.ReactNode){return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})}>{ui}</QueryClientProvider>)}
const review={id:"review-1",stars:5,comment:"Excellent professional service",moderation_status:"PENDING",moderation_reason:"",customer_display_name:"Asha",physiotherapist_name:"Priya",appointment_date:"2026-08-22T10:00:00Z",therapy_name:"Physiotherapy",created_at:"2026-08-22T11:00:00Z"};

describe("customer reviews",()=>{
  beforeEach(()=>{
    vi.restoreAllMocks();
    window.history.replaceState(null,"","/");
  });
  afterEach(()=>window.history.replaceState(null,"","/"));

  it("uses accessible stars and previews before one-time submission",async()=>{
    const submitted={...review,appointment:"appointment-1",status_display:"Pending Review"};
    let rating:typeof submitted|null=null;
    const fetchMock=vi.spyOn(global,"fetch").mockImplementation(async(input)=>String(input).includes("/rating")?(rating=submitted,new Response(JSON.stringify(submitted),{status:201})):new Response(JSON.stringify([{id:"appointment-1",status:"COMPLETED",assignment_status:"ACCEPTED",therapy_name:"Physiotherapy",physiotherapist_name:"Priya",scheduled_start:"2026-08-22T10:00:00Z",rating}]),{status:200}));
    renderQuery(<CustomerRatingPanel/>);
    fireEvent.click(await screen.findByRole("radio",{name:"5 stars"}));
    expect(screen.getByLabelText("Review (optional)")).not.toBeRequired();
    fireEvent.click(screen.getByRole("button",{name:"Review submission"}));
    expect(screen.getByText("Review before submitting")).toBeInTheDocument();
    expect(screen.getByText(/No written review/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button",{name:"Submit review"}));
    await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/rating"),expect.objectContaining({method:"POST"})));
    expect(await screen.findByText("Feedback submitted")).toBeInTheDocument();
    expect(screen.getByText("Physiotherapy · Priya")).toBeInTheDocument();
    expect(screen.queryByRole("button",{name:/submit|review submission/i})).not.toBeInTheDocument();
  });

  it("renders only backend-approved public reviews without fake fallback",async()=>{
    vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify({average_rating:5,review_count:1,reviews:[review]}),{status:200}));
    renderQuery(<PublicReviews/>);
    expect(await screen.findByText("Excellent professional service")).toBeInTheDocument();
    expect(screen.getByText("Asha")).toBeInTheDocument();
    expect(screen.getByText(/Priya/)).toBeInTheDocument();
  });

  it("lets an owner change public visibility while preserving review content",async()=>{
    vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify({results:[review]}),{status:200}));
    renderQuery(<ReviewModerationPanel/>);
    expect(await screen.findByText("Publicly visible: No")).toBeInTheDocument();
    expect(screen.getByRole("button",{name:"Make publicly visible"})).toBeEnabled();
    const hide=screen.getByRole("button",{name:"Keep private"});
    expect(hide).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Reason to hide"),{target:{value:"Private information"}});
    expect(hide).toBeEnabled();
  });

  it("persists submitted feedback state and therapist identity after reload",async()=>{
    vi.spyOn(global,"fetch").mockImplementation(async()=>new Response(JSON.stringify([{id:"appointment-1",status:"COMPLETED",assignment_status:"ACCEPTED",therapy_name:"Physiotherapy",physiotherapist_name:"Priya",scheduled_start:"2026-08-22T10:00:00Z",rating:{...review,appointment:"appointment-1",status_display:"Pending Review"}}]),{status:200}));
    const {unmount}=renderQuery(<CustomerRatingPanel/>);
    expect(await screen.findByText("Feedback submitted")).toBeInTheDocument();
    expect(screen.getByText("Physiotherapy · Priya")).toBeInTheDocument();
    expect(screen.queryByRole("button",{name:/submit|review submission/i})).not.toBeInTheDocument();
    unmount();
    renderQuery(<CustomerRatingPanel/>);
    expect(await screen.findByText("Feedback submitted")).toBeInTheDocument();
  });

  it("focuses the rating section when a same-page notification adds the hash",async()=>{
    const scrollIntoView=vi.fn();
    const focus=vi.spyOn(HTMLElement.prototype,"focus");
    Object.defineProperty(HTMLElement.prototype,"scrollIntoView",{configurable:true,value:scrollIntoView});
    vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify([{id:"appointment-1",status:"COMPLETED",assignment_status:"ACCEPTED",therapy_name:"Physiotherapy",physiotherapist_name:"Priya",scheduled_start:"2026-08-22T10:00:00Z",rating:null}]),{status:200}));
    renderQuery(<CustomerRatingPanel appointmentId="appointment-1"/>);
    const section=(await screen.findByRole("heading",{name:"Rate your therapist"})).closest("section");

    window.history.replaceState(null,"","/#rating");
    window.dispatchEvent(new HashChangeEvent("hashchange"));

    await waitFor(()=>expect(scrollIntoView).toHaveBeenCalled());
    expect(focus).toHaveBeenCalled();
    expect(section).toHaveFocus();
  });
});
