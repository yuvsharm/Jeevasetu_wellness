import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PractitionerLogin, PractitionerRegistration } from "./practitioner-auth";

const replace=vi.fn(); const refresh=vi.fn();
vi.mock("next/navigation",()=>({useRouter:()=>({replace,refresh}),useSearchParams:()=>new URLSearchParams()}));
vi.mock("@/lib/auth/msg91-widget",()=>({loadOtpWidgetConfig:async()=>({enabled:false}),sendMsg91Otp:vi.fn(),verifyMsg91Otp:vi.fn()}));

describe("practitioner authentication",()=>{
  beforeEach(()=>{vi.restoreAllMocks();replace.mockReset();refresh.mockReset();});

  it("uses mobile and password for returning practitioner login",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify({}),{status:200}));
    render(<PractitionerLogin/>);
    fireEvent.change(screen.getByLabelText("Mobile number"),{target:{value:"9876543210"}});
    fireEvent.change(screen.getByLabelText("Password"),{target:{value:"Secure-password-2026"}});
    fireEvent.click(screen.getByRole("button",{name:"Login"}));
    await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith("/api/session/login",expect.objectContaining({method:"POST"})));
    expect(replace).toHaveBeenCalledWith("/dashboard");
    expect(screen.getByRole("link",{name:/register \/ join/i})).toHaveAttribute("href","/therapist-register");
  });

  it("verifies OTP before creating or activating one practitioner account",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(async input=>{
      const url=String(input);
      if(url==="/api/booking-otp/issue")return new Response(JSON.stringify({verification_id:"verify-1"}),{status:201});
      if(url==="/api/booking-otp/verify")return new Response(JSON.stringify({token:"signed-proof"}),{status:200});
      return new Response(JSON.stringify({activated:false}),{status:201});
    });
    render(<PractitionerRegistration/>);
    fireEvent.change(screen.getByLabelText("Full Name"),{target:{value:"TEST Practitioner"}});
    fireEvent.change(screen.getByLabelText("Mobile Number"),{target:{value:"9876543210"}});
    fireEvent.click(screen.getByRole("button",{name:"Send OTP"}));
    fireEvent.change(await screen.findByLabelText("One-time password"),{target:{value:"123456"}});
    fireEvent.click(screen.getByRole("button",{name:"Verify Mobile"}));
    await screen.findByText("Mobile number verified");
    fireEvent.change(screen.getByLabelText("Password"),{target:{value:"Practitioner-Secure-2026!"}});
    fireEvent.change(screen.getByLabelText("Confirm Password"),{target:{value:"Practitioner-Secure-2026!"}});
    fireEvent.click(screen.getByRole("button",{name:"Create / Activate Account"}));
    await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith("/api/session/practitioner-register",expect.objectContaining({method:"POST"})));
    expect(replace).toHaveBeenCalledWith("/therapist-login?registered=1&returnTo=%2Fpractitioner-application");
  });
});
