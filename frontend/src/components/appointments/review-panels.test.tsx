import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CustomerRatingPanel } from "@/components/appointments/customer-rating";
import { PublicReviews, ReviewModerationPanel } from "@/components/appointments/review-panels";

function renderQuery(ui:React.ReactNode){return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})}>{ui}</QueryClientProvider>)}
const review={id:"review-1",stars:5,comment:"Excellent professional service",moderation_status:"PENDING",moderation_reason:"",customer_display_name:"Asha",physiotherapist_name:"Priya",appointment_date:"2026-08-22T10:00:00Z",therapy_name:"Physiotherapy",created_at:"2026-08-22T11:00:00Z"};

describe("customer reviews",()=>{
  beforeEach(()=>vi.restoreAllMocks());

  it("uses accessible stars and previews before one-time submission",async()=>{
    const fetchMock=vi.spyOn(global,"fetch").mockImplementation(async(input)=>String(input).includes("/rating")?new Response(JSON.stringify({...review,appointment:"appointment-1",status_display:"Pending Review"}),{status:201}):new Response(JSON.stringify([{id:"appointment-1",status:"COMPLETED",therapy_name:"Physiotherapy",scheduled_start:"2026-08-22T10:00:00Z",rating:null}]),{status:200}));
    renderQuery(<CustomerRatingPanel/>);
    fireEvent.click(await screen.findByRole("radio",{name:"5 stars"}));
    fireEvent.change(screen.getByLabelText("Comment"),{target:{value:"Excellent professional service"}});
    fireEvent.click(screen.getByRole("button",{name:"Review submission"}));
    expect(screen.getByText("Review before submitting")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button",{name:"Submit review"}));
    await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/rating"),expect.objectContaining({method:"POST"})));
  });

  it("renders only backend-approved public reviews without fake fallback",async()=>{
    vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify({average_rating:5,review_count:1,reviews:[review]}),{status:200}));
    renderQuery(<PublicReviews/>);
    expect(await screen.findByText("Excellent professional service")).toBeInTheDocument();
    expect(screen.getByText("Asha")).toBeInTheDocument();
    expect(screen.getByText(/Priya/)).toBeInTheDocument();
  });

  it("requires a reason before enabling hide",async()=>{
    vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify({results:[review]}),{status:200}));
    renderQuery(<ReviewModerationPanel/>);
    const hide=await screen.findByRole("button",{name:"Hide / Reject"});
    expect(hide).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Reason to hide/reject"),{target:{value:"Private information"}});
    expect(hide).toBeEnabled();
  });
});
