import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PractitionerVisitWorkflow } from "./practitioner-visit-workflow";

const offer = { id: "visit-1", patient_name: "Service request", therapy_name: "Physiotherapy", duration_minutes: 60, scheduled_start: "2026-08-12T10:00:00Z", city: "Meerut", region: "Uttar Pradesh", assignment_status: "PENDING", status: "SCHEDULED", journey_status: "NOT_STARTED" };
function mount() { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><PractitionerVisitWorkflow /></QueryClientProvider>); }

it("shows a minimal offer and requires a structured decline reason", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => init?.method === "POST" ? new Response(JSON.stringify(offer), { status: 200 }) : new Response(JSON.stringify([offer]), { status: 200 }));
  mount(); expect(await screen.findByText("New Service Request")).toBeInTheDocument(); expect(screen.queryByText(/mobile/i)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Decline" }));
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "Reason" }), "too far");
  await userEvent.click(screen.getByRole("button", { name: "Confirm rejection" }));
  expect(fetchMock).toHaveBeenCalledWith("/api/schedule/visit-1/assignment-response", expect.objectContaining({ body: JSON.stringify({ id: "visit-1", accept: false, reason: "too far" }) }));
});

it("starts the session directly after the therapist is en route",async()=>{
  const enRoute={...offer,patient_name:"Ravi Kumar",assignment_status:"ACCEPTED",status:"CONFIRMED",journey_status:"EN_ROUTE"};
  const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(async(_input,init)=>new Response(JSON.stringify(init?.method==="POST"?{...enRoute,status:"IN_PROGRESS"}:[enRoute]),{status:200}));
  mount();await userEvent.click(await screen.findByRole("button",{name:"Start Session"}));
  expect(fetchMock).toHaveBeenCalledWith("/api/schedule/visit-1/status",expect.objectContaining({method:"POST",body:JSON.stringify({status:"IN_PROGRESS"})}));
  expect(screen.queryByText(/otp/i)).not.toBeInTheDocument();
});

it("shows the exact owner QR and UPI, copies the ID, and confirms completion once",async()=>{
  const active={...offer,patient_name:"Ravi Kumar",assignment_status:"ACCEPTED",status:"IN_PROGRESS",journey_status:"EN_ROUTE",payment_amount_due:"1777.00",payment_status:"PENDING"};
  const completed={...active,status:"COMPLETED",payment_status:"PAID",payment_paid_at:"2026-08-12T11:00:00Z"};
  let current=active;
  const writeText=vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator,"clipboard",{value:{writeText},configurable:true});
  const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(async(input,init)=>{if(init?.method==="POST"&&String(input).endsWith("/complete-and-confirm-payment"))current=completed;return new Response(JSON.stringify(init?.method==="POST"?current:[current]),{status:200})});
  mount();
  expect(await screen.findByRole("heading",{name:"Payment to JeevaSetu / Owner"})).toBeInTheDocument();
  expect(screen.getByText("Amount: ₹1777.00")).toBeInTheDocument();
  expect(screen.getByText("7351150555@ptsbi")).toBeInTheDocument();
  expect(screen.getByRole("img",{name:"JeevaSetu owner UPI payment QR code"})).toHaveAttribute("src","/images/payments/jeevasetu-owner-upi-qr.png");
  await userEvent.click(screen.getByRole("button",{name:"Copy UPI ID"}));
  expect(writeText).toHaveBeenCalledWith("7351150555@ptsbi");
  expect(await screen.findByText("UPI ID copied.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button",{name:"Complete Therapy & Confirm Payment"}));
  const confirm=screen.getByRole("button",{name:"Confirm Completion & Payment"});
  expect(confirm).toBeDisabled();
  await userEvent.click(screen.getByRole("checkbox",{name:"Therapy/service was delivered"}));
  await userEvent.click(screen.getByRole("checkbox",{name:"Customer showed successful owner payment confirmation"}));
  await userEvent.click(confirm);
  await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith("/api/schedule/visit-1/complete-and-confirm-payment",expect.objectContaining({method:"POST",body:JSON.stringify({therapy_delivered:true,payment_received:true})})));
  expect(fetchMock.mock.calls.filter(([input,init])=>String(input).endsWith("/complete-and-confirm-payment")&&init?.method==="POST")).toHaveLength(1);
});

it("shows the final completed and confirmed state without another confirmation action",async()=>{
  const completed={...offer,patient_name:"Ravi Kumar",assignment_status:"ACCEPTED",status:"COMPLETED",journey_status:"EN_ROUTE",payment_amount_due:"1777.00",payment_status:"PAID",payment_paid_at:"2026-08-12T11:00:00Z"};
  vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify([completed]),{status:200}));
  mount();expect(await screen.findByText("Appointment completed successfully · Payment confirmed")).toBeInTheDocument();expect(screen.getByText("Amount: ₹1777.00")).toBeInTheDocument();expect(screen.getByText("Payment confirmed")).toBeInTheDocument();expect(screen.queryByRole("button",{name:"Complete Therapy & Confirm Payment"})).not.toBeInTheDocument();
});
