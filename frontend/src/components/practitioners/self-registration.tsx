"use client";

import Link from "next/link";
import {useQuery} from "@tanstack/react-query";
import {StaffCreationWizard} from "@/components/staff/staff-creation-wizard";
import {requestJson} from "@/lib/api/client";

type Options = {clinics:{id:string;slug:string}[];therapies:{id:string;name:string}[];service_areas:{id:string;name:string}[]};
export function PractitionerRegistration(){
  const options=useQuery({queryKey:["practitioner-registration-options"],queryFn:()=>requestJson<Options>("/api/practitioners/registration-options")});
  return <div>{options.isPending?<p role="status">Loading application options…</p>:options.isError?<div role="alert"><p>Application options could not be loaded. Please try again.</p><button className="button-secondary" onClick={()=>options.refetch()}>Try again</button></div>:<StaffCreationWizard role="PHYSIOTHERAPIST" clinics={options.data.clinics} therapies={options.data.therapies} serviceAreas={options.data.service_areas} selfApplication onCreated={()=>{}}/>}<p className="mt-6 text-center">Already registered? <Link className="font-bold text-emerald-800" href="/therapist-login">Sign In</Link></p></div>;
}
