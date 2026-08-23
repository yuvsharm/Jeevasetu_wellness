import { QueryClient,QueryClientProvider } from "@tanstack/react-query";
import { fireEvent,render,screen } from "@testing-library/react";
import { afterEach,describe,expect,it,vi } from "vitest";

import { OwnerAnalyticsDashboard } from "@/components/analytics/owner-analytics-dashboard";

const data={scope:{preset:"last_30_days",start_date:"2026-08-01",end_date:"2026-08-23",timezone:"Asia/Kolkata"},definitions:{booked_value:"Snapshot amounts.",repeat_customer:"Two requests.",payment_position:"Payouts."},kpis:{total_requests:4,total_scheduled:3,pending:0,confirmed:1,in_progress:0,completed:2,cancelled:0,customers:2,repeat_customers:1,active_therapists:1,average_approved_rating:5,booked_value:"2500.00",completed_service_value:"1800.00",total_discounts:"200.00"},appointments:{completion_rate:66.7,cancellation_rate:0,statuses:{COMPLETED:2,CONFIRMED:1},request_statuses:{APPROVED:3}},growth:[{date:"2026-08-23",bookings:2,completed:1,booked_value:"1800.00",customers:1}],practitioner_payments:{PENDING:{count:1,amount:"500.00"},PROCESSING:{count:0,amount:"0.00"},PAID:{count:1,amount:"700.00"},HELD:{count:0,amount:"0.00"}},therapies:[{id:"1",name:"Kati Basti",bookings:2,completed:1,booked_value:"1800.00",average_rating:5}],commercial_performance:[{kind:"PACKAGE",name:"7 Session Plan",bookings:1,booked_value:"7000.00",discounts:"1400.00",average_discount:"1400.00",completed:1,completion_rate:100}],customers:{total:2,new:1,repeat:1,repeat_rate:50,self_bookings:3,family_bookings:1,average_completed_per_returning_customer:2},therapists:[{id:"1",name:"Asha Therapist",assigned:3,accepted:2,rejected:1,completed:2,active_workload:1,acceptance_rate:66.7,completion_rate:66.7,average_rating:5,review_count:1}],reviews:{average:5,count:1,distribution:{"1":0,"2":0,"3":0,"4":0,"5":1},trend:[],recent:[{stars:5,comment:"Excellent",created_at:"2026-08-23T10:00:00Z",therapy:"Kati Basti"}]},attention:{pending_requests:1,awaiting_therapist:0,therapist_rejections:1,overdue_appointments:0,pending_practitioner_payments:1,pending_review_moderation:0,pending_practitioner_applications:1}};
function wrap(){return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><OwnerAnalyticsDashboard/></QueryClientProvider>)}

describe("OwnerAnalyticsDashboard",()=>{
  afterEach(()=>vi.restoreAllMocks());
  it("renders commercially accurate owner KPIs and strategic tables",async()=>{
    vi.spyOn(global,"fetch").mockImplementation(async()=>new Response(JSON.stringify(data),{status:200}));
    wrap();
    expect(await screen.findByText("Business analytics")).toBeInTheDocument();
    expect(await screen.findByText("₹2,500")).toBeInTheDocument();
    expect(screen.getByText(/Booked value is not revenue/)).toBeInTheDocument();
    expect(screen.getByText("Kati Basti")).toBeInTheDocument();
    expect(screen.getByText("Asha Therapist")).toBeInTheDocument();
    expect(screen.getByText("7 Session Plan")).toBeInTheDocument();
  });
  it("applies one custom range to the backend query",async()=>{
    const fetchMock=vi.spyOn(global,"fetch").mockImplementation(async()=>new Response(JSON.stringify(data),{status:200}));
    wrap();
    await screen.findByText("Business growth");
    fireEvent.change(screen.getByLabelText("Date range"),{target:{value:"custom"}});
    fireEvent.change(screen.getByLabelText("Start"),{target:{value:"2026-08-01"}});
    fireEvent.change(screen.getByLabelText("End"),{target:{value:"2026-08-23"}});
    expect(await screen.findByText("Business growth")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("preset=custom&start=2026-08-01&end=2026-08-23"),expect.anything());
  });
});
