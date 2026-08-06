import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PatientDirectory } from "@/components/patients/patient-management";

function wrap() {
  return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><PatientDirectory /></QueryClientProvider>);
}

describe("patient management", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("provides minimal patient search, status filtering and creation", () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({count:0,next:null,previous:null,results:[]}), {status:200}));
    wrap();
    expect(screen.getByLabelText("Search patients")).toBeInTheDocument();
    expect(screen.getByLabelText("Filter patient status")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", {name:"Add patient"}));
    expect(screen.getByRole("form", {name:"Create patient"})).toBeInTheDocument();
    expect(screen.getByText("Guardian details (mandatory below age 18)")).toBeInTheDocument();
  });

  it("shows masked mobile data in the directory", async () => {
    const patient = {id:"1",patient_identifier:"PAT-000001",full_name:"Asha Sharma",mobile_hint:"******3210",gender:"FEMALE",date_of_birth:null,age:28,clinic:"c1",clinic_name:"Meerut",is_active:true};
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({count:1,next:null,previous:null,results:[patient]}), {status:200}));
    wrap();
    expect(await screen.findByText("Asha Sharma")).toBeInTheDocument();
    expect(screen.getByText(/PAT-000001/)).toHaveTextContent("******3210");
  });
});
