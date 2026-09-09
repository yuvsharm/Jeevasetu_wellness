import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {QueryClient,QueryClientProvider} from "@tanstack/react-query";

import { PractitionerLogin } from "./practitioner-auth";

const replace=vi.fn(); const refresh=vi.fn();
vi.mock("next/navigation",()=>({useRouter:()=>({replace,refresh}),useSearchParams:()=>new URLSearchParams()}));
vi.mock("@/lib/auth/msg91-widget",()=>({loadOtpWidgetConfig:async()=>({enabled:false}),sendMsg91Otp:vi.fn(),verifyMsg91Otp:vi.fn()}));

describe("practitioner authentication",()=>{
  beforeEach(()=>{vi.restoreAllMocks();replace.mockReset();refresh.mockReset();});

  it("uses mobile and password for returning practitioner login",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify({user:{},access:{roles:[]}}),{status:200}));
    const client=new QueryClient();render(<QueryClientProvider client={client}><PractitionerLogin/></QueryClientProvider>);
    expect(screen.getByText("Enter your registered 10-digit Indian mobile number.")).toBeInTheDocument();
    expect(screen.getByRole("link",{name:"Forgot Password?"})).toHaveAttribute("href","/forgot-password?context=therapist");
    fireEvent.change(screen.getByLabelText("Mobile number"),{target:{value:"9876543210"}});
    fireEvent.change(screen.getByLabelText("Password"),{target:{value:"Secure-password-2026"}});
    fireEvent.click(screen.getByRole("button",{name:"Sign In"}));
    await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith("/api/session/login",expect.objectContaining({method:"POST"})));
    expect(replace).toHaveBeenCalledWith("/dashboard");
    expect(client.getQueryData(["session"])).toEqual({user:{},access:{roles:[]}});
    expect(screen.getByRole("link",{name:/new practitioner/i})).toHaveAttribute("href","/therapist-register");
  });

});
