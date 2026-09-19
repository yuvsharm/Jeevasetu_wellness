import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach } from "vitest";
import { PractitionerVisitWorkflow } from "./practitioner-visit-workflow";

const offer = { id: "visit-1", patient_name: "Meera Relative", patient_age: 67, patient_mobile: "9876543210", therapy_name: "Physiotherapy", requested_therapy_names: ["Physiotherapy", "Kati Basti"], duration_minutes: 60, scheduled_start: "2026-08-12T10:00:00Z", address_line_1: "163 C Block", address_line_2: "First floor", landmark: "Near park", city: "Meerut", region: "Uttar Pradesh", pin_code: "250004", assignment_status: "PENDING", status: "SCHEDULED", journey_status: "NOT_STARTED" };
function mount() { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><PractitionerVisitWorkflow /></QueryClientProvider>); }
afterEach(() => vi.restoreAllMocks());

it("shows the assigned patient, booking contact, and full address before acceptance", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => init?.method === "POST" ? new Response(JSON.stringify(offer), { status: 200 }) : new Response(JSON.stringify([offer]), { status: 200 }));
  mount(); expect(await screen.findByRole("heading", { name: "Meera Relative" })).toBeInTheDocument();
  expect(screen.getByText("Meera Relative · Age 67")).toBeInTheDocument();
  expect(screen.getByText("9876543210")).toBeInTheDocument();
  expect(screen.getByText("163 C Block, First floor, Near park, Meerut, Uttar Pradesh, 250004")).toBeInTheDocument();
  expect(screen.getByText("Physiotherapy, Kati Basti · 60 minutes")).toBeInTheDocument();
  expect(screen.getByText("AWAITING ACCEPTANCE")).toBeInTheDocument();
  expect(screen.queryByText("VISIT-1")).not.toBeInTheDocument();
  expect(screen.getByText("Patient").closest("dl")).toHaveClass("sm:grid-cols-2");
  expect(screen.getByText("Service address").parentElement).toHaveClass("sm:col-span-2");
  await userEvent.click(screen.getByRole("button", { name: "Decline" }));
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "Reason" }), "too far");
  await userEvent.click(screen.getByRole("button", { name: "Confirm rejection" }));
  expect(fetchMock).toHaveBeenCalledWith("/api/schedule/visit-1/assignment-response", expect.objectContaining({ body: JSON.stringify({ id: "visit-1", accept: false, reason: "too far" }) }));
});

it.each([
  ["pending", { assignment_status: "PENDING", status: "SCHEDULED" }],
  ["accepted", { assignment_status: "ACCEPTED", status: "CONFIRMED" }],
  ["active", { assignment_status: "ACCEPTED", status: "IN_PROGRESS", journey_status: "REACHED" }],
  ["completed", { assignment_status: "ACCEPTED", status: "COMPLETED", payment_status: "PAID" }],
])("keeps canonical service identity on %s cards", async (_label, state) => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify([{ ...offer, ...state }]), { status: 200 }));
  mount();
  expect(await screen.findByRole("heading", { name: "Meera Relative" })).toBeInTheDocument();
  expect(screen.getByText("Meera Relative · Age 67")).toBeInTheDocument();
  expect(screen.getByText("9876543210")).toBeInTheDocument();
  expect(screen.getByText("163 C Block, First floor, Near park, Meerut, Uttar Pradesh, 250004")).toBeInTheDocument();
});

it("requires Reached between En Route and starting therapy",async()=>{
  const enRoute={...offer,patient_name:"Ravi Kumar",assignment_status:"ACCEPTED",status:"CONFIRMED",journey_status:"EN_ROUTE"};
  const reached={...enRoute,journey_status:"REACHED"};
  let current=enRoute;
  const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(async(input,init)=>{if(init?.method==="POST"&&String(input).endsWith("/journey"))current=reached;else if(init?.method==="POST")current={...reached,status:"IN_PROGRESS"};return new Response(JSON.stringify(init?.method==="POST"?current:[current]),{status:200})});
  mount();expect(await screen.findByRole("button",{name:"Reached"})).toBeInTheDocument();
  expect(screen.queryByRole("button",{name:"Start Session"})).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button",{name:"Reached"}));
  await userEvent.click(await screen.findByRole("button",{name:"Start Session"}));
  expect(fetchMock).toHaveBeenCalledWith("/api/schedule/visit-1/journey",expect.objectContaining({method:"POST",body:JSON.stringify({journey_status:"REACHED"})}));
  expect(fetchMock).toHaveBeenCalledWith("/api/schedule/visit-1/status",expect.objectContaining({method:"POST",body:JSON.stringify({status:"IN_PROGRESS"})}));
  expect(screen.queryByText(/otp/i)).not.toBeInTheDocument();
});

it("shows the exact owner QR and UPI, copies the ID, and confirms completion once",async()=>{
  const active={...offer,patient_name:"Ravi Kumar",assignment_status:"ACCEPTED",status:"IN_PROGRESS",journey_status:"REACHED",payment_amount_due:"1777.00",payment_status:"PENDING"};
  const completed={...active,status:"COMPLETED",payment_status:"PAID",payment_paid_at:"2026-08-12T11:00:00Z"};
  let current=active;
  const writeText=vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator,"clipboard",{value:{writeText},configurable:true});
  const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(async(input,init)=>{if(init?.method==="POST"&&String(input).endsWith("/complete-and-confirm-payment"))current=completed;return new Response(JSON.stringify(init?.method==="POST"?current:[current]),{status:200})});
  mount();
  expect(await screen.findByText("Payment pending · ₹1777.00")).toBeInTheDocument();
  expect(screen.queryByRole("heading",{name:"Payment to JeevaSetu / Owner"})).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button",{name:"Show Payment QR"}));
  expect(screen.getByRole("dialog",{name:"Payment to JeevaSetu / Owner"})).toBeInTheDocument();
  expect(screen.getByText("Amount: ₹1777.00")).toBeInTheDocument();
  expect(screen.getByText("7351150555@ptsbi")).toBeInTheDocument();
  expect(screen.queryByText("AG")).not.toBeInTheDocument();
  expect(screen.queryByText("Anuj Gaur")).not.toBeInTheDocument();
  expect(screen.getByRole("img",{name:"JeevaSetu owner UPI payment QR code"})).toHaveAttribute("src","/images/payments/jeevasetu-owner-upi-qr.png");
  await userEvent.click(screen.getByRole("button",{name:"Copy"}));
  expect(writeText).toHaveBeenCalledWith("7351150555@ptsbi");
  expect(await screen.findByText("UPI ID copied.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button",{name:"Close payment QR"}));
  expect(screen.queryByRole("dialog",{name:"Payment to JeevaSetu / Owner"})).not.toBeInTheDocument();
  expect(screen.getByRole("button",{name:"Show Payment QR"})).toHaveFocus();
  await userEvent.click(screen.getByRole("button",{name:"Complete Therapy & Confirm Payment"}));
  const confirm=screen.getByRole("button",{name:"Confirm Completion & Payment"});
  expect(confirm).toBeDisabled();
  await userEvent.click(screen.getByRole("checkbox",{name:"Therapy/service was delivered"}));
  await userEvent.click(screen.getByRole("checkbox",{name:"Customer showed successful owner payment confirmation"}));
  await userEvent.click(confirm);
  await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith("/api/schedule/visit-1/complete-and-confirm-payment",expect.objectContaining({method:"POST",body:JSON.stringify({therapy_delivered:true,payment_received:true})})));
  expect(fetchMock.mock.calls.filter(([input,init])=>String(input).endsWith("/complete-and-confirm-payment")&&init?.method==="POST")).toHaveLength(1);
  await waitFor(()=>expect(screen.queryByRole("dialog",{name:"Confirm completion and payment"})).not.toBeInTheDocument());
  expect(await screen.findByText("Appointment completed successfully · Payment confirmed")).toBeInTheDocument();
  expect(screen.queryByRole("button",{name:"Complete Therapy & Confirm Payment"})).not.toBeInTheDocument();
});

it("opens one QR modal with the selected appointment amount and Escape changes no state",async()=>{
  const first={...offer,id:"visit-1",patient_name:"Ravi Kumar",assignment_status:"ACCEPTED",status:"IN_PROGRESS",journey_status:"REACHED",payment_amount_due:"1777.00",payment_status:"PENDING"};
  const second={...first,id:"visit-2",patient_name:"Asha Sharma",payment_amount_due:"2450.00"};
  const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify([first,second]),{status:200}));
  mount();
  const buttons=await screen.findAllByRole("button",{name:"Show Payment QR"});
  fetchMock.mockClear();
  await userEvent.click(buttons[1]);
  expect(screen.getAllByRole("dialog",{name:"Payment to JeevaSetu / Owner"})).toHaveLength(1);
  expect(screen.getByText("Amount: ₹2450.00")).toBeInTheDocument();
  expect(screen.queryByText("Amount: ₹1777.00")).not.toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog",{name:"Payment to JeevaSetu / Owner"})).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.filter(([,init])=>init?.method==="POST")).toHaveLength(0);
});

it.each([400,401,403,404,409,500])("keeps the confirmation modal open after an HTTP %s failure",async(status)=>{
  const active={...offer,patient_name:"Ravi Kumar",assignment_status:"ACCEPTED",status:"IN_PROGRESS",journey_status:"REACHED",payment_amount_due:"1777.00",payment_status:"PENDING"};
  vi.spyOn(globalThis,"fetch").mockImplementation(async(input,init)=>init?.method==="POST"&&String(input).endsWith("/complete-and-confirm-payment")?new Response(JSON.stringify({detail:"Payment confirmation failed. Please retry."}),{status}):new Response(JSON.stringify([active]),{status:200}));
  mount();await userEvent.click(await screen.findByRole("button",{name:"Complete Therapy & Confirm Payment"}));
  await userEvent.click(screen.getByRole("checkbox",{name:"Therapy/service was delivered"}));
  await userEvent.click(screen.getByRole("checkbox",{name:"Customer showed successful owner payment confirmation"}));
  await userEvent.click(screen.getByRole("button",{name:"Confirm Completion & Payment"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("Payment confirmation failed. Please retry.");
  expect(screen.getByRole("dialog",{name:"Confirm completion and payment"})).toBeInTheDocument();
  expect(screen.queryByText("Appointment completed successfully · Payment confirmed")).not.toBeInTheDocument();
});

it("prevents duplicate completion submission while the canonical request is pending",async()=>{
  const active={...offer,patient_name:"Ravi Kumar",assignment_status:"ACCEPTED",status:"IN_PROGRESS",journey_status:"REACHED",payment_amount_due:"1777.00",payment_status:"PENDING"};
  const completed={...active,status:"COMPLETED",payment_status:"PAID",payment_paid_at:"2026-08-12T11:00:00Z"};
  let current=active;
  let resolveCompletion!: (response: Response) => void;
  const pendingCompletion=new Promise<Response>((resolve)=>{resolveCompletion=resolve;});
  const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(async(input,init)=>{
    if(init?.method==="POST"&&String(input).endsWith("/complete-and-confirm-payment"))return pendingCompletion;
    return new Response(JSON.stringify([current]),{status:200});
  });
  mount();await userEvent.click(await screen.findByRole("button",{name:"Complete Therapy & Confirm Payment"}));
  await userEvent.click(screen.getByRole("checkbox",{name:"Therapy/service was delivered"}));
  await userEvent.click(screen.getByRole("checkbox",{name:"Customer showed successful owner payment confirmation"}));
  await userEvent.click(screen.getByRole("button",{name:"Confirm Completion & Payment"}));
  const pendingButton=await screen.findByRole("button",{name:"Confirming…"});
  expect(pendingButton).toBeDisabled();
  await userEvent.click(pendingButton);
  expect(fetchMock.mock.calls.filter(([input,init])=>String(input).endsWith("/complete-and-confirm-payment")&&init?.method==="POST")).toHaveLength(1);
  current=completed;
  resolveCompletion(new Response(JSON.stringify(completed),{status:200}));
  await waitFor(()=>expect(screen.queryByRole("dialog",{name:"Confirm completion and payment"})).not.toBeInTheDocument());
  expect(await screen.findByText("Appointment completed successfully · Payment confirmed")).toBeInTheDocument();
});

it("keeps canonical active state after a network failure",async()=>{
  const active={...offer,patient_name:"Ravi Kumar",assignment_status:"ACCEPTED",status:"IN_PROGRESS",journey_status:"REACHED",payment_amount_due:"1777.00",payment_status:"PENDING"};
  vi.spyOn(globalThis,"fetch").mockImplementation(async(input,init)=>{if(init?.method==="POST"&&String(input).endsWith("/complete-and-confirm-payment"))throw new TypeError("network offline");return new Response(JSON.stringify([active]),{status:200})});
  mount();await userEvent.click(await screen.findByRole("button",{name:"Complete Therapy & Confirm Payment"}));
  await userEvent.click(screen.getByRole("checkbox",{name:"Therapy/service was delivered"}));
  await userEvent.click(screen.getByRole("checkbox",{name:"Customer showed successful owner payment confirmation"}));
  await userEvent.click(screen.getByRole("button",{name:"Confirm Completion & Payment"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("The service is unavailable. Check your connection and retry.");
  expect(screen.getByRole("dialog",{name:"Confirm completion and payment"})).toBeInTheDocument();
  expect(screen.queryByText("Appointment completed successfully · Payment confirmed")).not.toBeInTheDocument();
});

it("shows the final completed and confirmed state without another payment request",async()=>{
  const completed={...offer,patient_name:"Ravi Kumar",assignment_status:"ACCEPTED",status:"COMPLETED",journey_status:"EN_ROUTE",payment_amount_due:"1777.00",payment_status:"PAID",payment_paid_at:"2026-08-12T11:00:00Z"};
  vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify([completed]),{status:200}));
  mount();expect(await screen.findByText("Appointment completed successfully · Payment confirmed")).toBeInTheDocument();expect(screen.getByText("Amount: ₹1777.00")).toBeInTheDocument();expect(screen.getByText("Payment confirmed")).toBeInTheDocument();expect(screen.queryByRole("button",{name:"Show Payment QR"})).not.toBeInTheDocument();expect(screen.queryByRole("button",{name:"Complete Therapy & Confirm Payment"})).not.toBeInTheDocument();
});
