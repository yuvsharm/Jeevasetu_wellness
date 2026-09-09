import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CustomerPasswordReset } from "./customer-password-reset";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/auth/msg91-widget", () => ({ loadOtpWidgetConfig: vi.fn(async () => ({ enabled: true, widgetId: "present", tokenAuth: "present" })), sendMsg91Otp: vi.fn(async () => undefined), verifyMsg91Otp: vi.fn(async () => "header.payload.signature") }));

describe("customer password reset", () => {
  it.each(["customer","therapist","staff"] as const)("verifies mobile and returns %s to the correct login", async (context) => {
    const fetchMock = vi.spyOn(global, "fetch").mockImplementation(async (input) => new Response(JSON.stringify(String(input).includes("/verify") ? {token:"signed-proof"} : String(input).includes("booking-otp") ? { verification_id: "verification-1" } : { detail: "ok" }), { status: 200 }));
    render(<CustomerPasswordReset context={context}/>);
    expect(screen.getByText("Enter your registered 10-digit Indian mobile number.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Mobile number"), { target: { value: "9876543210" } });
    fireEvent.click(screen.getByRole("button", { name: "Send OTP" }));
    fireEvent.change(await screen.findByLabelText("One-time password"), { target: { value: "654321" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify mobile" }));
    fireEvent.change(await screen.findByLabelText("New password"), { target: { value: "Replacement-Password-2026!" } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "Replacement-Password-2026!" } });
    fireEvent.click(screen.getByRole("button", { name: "Reset password" }));
    await screen.findByText("Password reset successfully. Please sign in with your new password.");
    expect(screen.getByRole("link",{name:"Sign in"})).toHaveAttribute("href",context==="customer"?"/customer-login?returnTo=%2Fcustomer":context==="therapist"?"/therapist-login":"/login");
    const call = fetchMock.mock.calls.find(([input]) => String(input) === (context==="customer"?"/api/session/customer-password-reset":"/api/session/account-password-reset"));
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body).toMatchObject({ verification_id: "verification-1", mobile_number: "9876543210", booking_verification_token: "signed-proof", new_password: "Replacement-Password-2026!" });
    expect(body).not.toHaveProperty("otp");
  });
  it("does not open password entry after failed OTP verification",async()=>{
    vi.spyOn(global,"fetch").mockImplementation(async input=>new Response(JSON.stringify(String(input).includes("/verify")?{detail:"Verification expired. Please request a new OTP."}:{verification_id:"v"}),{status:String(input).includes("/verify")?400:200}));
    render(<CustomerPasswordReset context="staff"/>);
    fireEvent.change(screen.getByLabelText("Mobile number"),{target:{value:"9876543210"}});fireEvent.click(screen.getByRole("button",{name:"Send OTP"}));fireEvent.change(await screen.findByLabelText("One-time password"),{target:{value:"123456"}});fireEvent.click(screen.getByRole("button",{name:"Verify mobile"}));await screen.findByRole("alert");expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
  });
  it("normalizes a pasted +91 number before issuing OTP",async()=>{
    const fetchMock=vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify({verification_id:"v"}),{status:200}));
    render(<CustomerPasswordReset context="therapist"/>);
    fireEvent.change(screen.getByLabelText("Mobile number"),{target:{value:"+91 9876543210"}});
    expect(screen.getByLabelText("Mobile number")).toHaveValue("9876543210");
    fireEvent.click(screen.getByRole("button",{name:"Send OTP"}));
    await screen.findByLabelText("One-time password");
    const issued=fetchMock.mock.calls.find(([input])=>String(input)==="/api/booking-otp/issue");
    expect(JSON.parse(String(issued?.[1]?.body))).toEqual({mobile_number:"9876543210"});
  });
  it("shows the backend password validation message instead of a generic error",async()=>{
    vi.spyOn(global,"fetch").mockImplementation(async input=>{
      const url=String(input);
      if(url.includes("booking-otp/issue"))return new Response(JSON.stringify({verification_id:"v"}),{status:200});
      if(url.includes("booking-otp/verify"))return new Response(JSON.stringify({token:"signed-proof"}),{status:200});
      return new Response(JSON.stringify({detail:"Please review the highlighted information.",fieldErrors:{new_password:"This password is too common."}}),{status:400});
    });
    render(<CustomerPasswordReset context="customer"/>);
    fireEvent.change(screen.getByLabelText("Mobile number"),{target:{value:"9876543210"}});fireEvent.click(screen.getByRole("button",{name:"Send OTP"}));
    fireEvent.change(await screen.findByLabelText("One-time password"),{target:{value:"123456"}});fireEvent.click(screen.getByRole("button",{name:"Verify mobile"}));
    fireEvent.change(await screen.findByLabelText("New password"),{target:{value:"Password1!"}});fireEvent.change(screen.getByLabelText("Confirm new password"),{target:{value:"Password1!"}});fireEvent.click(screen.getByRole("button",{name:"Reset password"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("This password is too common.");
  });
});
