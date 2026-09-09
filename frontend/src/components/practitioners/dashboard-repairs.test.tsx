import {QueryClient, QueryClientProvider} from "@tanstack/react-query";
import {fireEvent, render, screen, waitFor} from "@testing-library/react";
import {afterEach, expect, it, vi} from "vitest";
import {OpenToWorkControl} from "./open-to-work";
import {DobEditor} from "./dob-editor";

afterEach(()=>vi.restoreAllMocks());
function wrap(ui:React.ReactNode){
 const client=new QueryClient({defaultOptions:{queries:{retry:false}}});
 return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}
it("loads the canonical work state and saves both directions without an application",async()=>{
 const fetchMock=vi.spyOn(global,"fetch").mockImplementation(async(_url,init)=>new Response(JSON.stringify({is_open_to_work:init?.method==="POST"?JSON.parse(String(init.body)).enabled:true})));
 wrap(<OpenToWorkControl/>);
 const toggle=screen.getByRole("switch",{name:"Open to Work"});
 await waitFor(()=>expect(toggle).toHaveAttribute("aria-checked","true"));
 fireEvent.click(toggle);
 await waitFor(()=>expect(toggle).toHaveAttribute("aria-checked","false"));
 expect(screen.getByText("Not accepting new assignments. Existing visits remain active.")).toBeInTheDocument();
 fireEvent.click(toggle);
 await waitFor(()=>expect(toggle).toHaveAttribute("aria-checked","true"));
 expect(fetchMock.mock.calls.filter(([,init])=>init?.method==="POST").map(([,init])=>JSON.parse(String(init?.body)))).toEqual([{enabled:false},{enabled:true}]);
 expect(screen.queryByText(/only after approval/)).not.toBeInTheDocument();
});
it("shows the actual failure and preserves the saved state",async()=>{
 vi.spyOn(global,"fetch").mockImplementation(async(_url,init)=>init?.method==="POST"?new Response(JSON.stringify({detail:"An active therapist role and clinic membership are required."}),{status:403}):new Response(JSON.stringify({is_open_to_work:true})));
 wrap(<OpenToWorkControl/>);
 const toggle=screen.getByRole("switch");
 await waitFor(()=>expect(toggle).not.toBeDisabled());
 fireEvent.click(toggle);
 expect(await screen.findByRole("alert")).toHaveTextContent("An active therapist role and clinic membership are required.");
 expect(toggle).toHaveAttribute("aria-checked","true");
});
it("submits only ISO DOB and exposes field validation errors",async()=>{
 const fetchMock=vi.spyOn(global,"fetch").mockResolvedValue(new Response(JSON.stringify({date_of_birth:["Enter a valid date of birth."]}),{status:400}));
 wrap(<DobEditor dob={null} age={null} url="/api/staff/me"/>);
 fireEvent.click(screen.getByRole("button",{name:"Edit Date of Birth"}));
 fireEvent.change(screen.getByLabelText("Date of Birth *"),{target:{value:"1995-08-15"}});
 fireEvent.click(screen.getByRole("button",{name:"Save Date of Birth"}));
 expect(await screen.findByRole("alert")).toHaveTextContent("Enter a valid date of birth.");
 expect(fetchMock).toHaveBeenCalledWith("/api/staff/me",expect.objectContaining({method:"PATCH",body:'{"date_of_birth":"1995-08-15"}'}));
});
