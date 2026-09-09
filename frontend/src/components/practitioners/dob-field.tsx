"use client";
import {useEffect,useState} from "react";
import {requestJson,ClientApiError} from "@/lib/api/client";
export function dobError(error:unknown){return error instanceof ClientApiError?Object.values(error.fieldErrors??{}).join(" ")||error.message:error instanceof Error?error.message:"Enter a valid date of birth.";}
export async function validateDob(value:string,signal?:AbortSignal){if(!value)throw new Error("Date of birth is required.");return requestJson<{age:number}>("/api/practitioners/dob-preview",{method:"POST",body:JSON.stringify({date_of_birth:value}),signal});}
export function formatDob(value:string|null|undefined){return value?new Intl.DateTimeFormat("en-GB",{day:"numeric",month:"short",year:"numeric",timeZone:"UTC"}).format(new Date(`${value}T12:00:00Z`)):"DOB required";}
export function DobField({value,onChange}:{value:string;onChange:(value:string)=>void}){return <label className="grid gap-2 font-semibold">Date of Birth *<input id="date-of-birth" aria-label="Date of Birth *" type="date" required value={value} onChange={e=>onChange(e.target.value)} className="min-h-12 rounded-xl border border-slate-300 px-3"/><span className="text-sm font-normal text-slate-600">Therapists must be 18–80 years old. Your date of birth is private.</span></label>;}
export function DobReview({value}:{value:string}){
 const [result,setResult]=useState<{value:string;age?:number;error?:string}>();
 useEffect(()=>{const controller=new AbortController();if(value)validateDob(value,controller.signal).then(data=>setResult({value,age:data.age})).catch(error=>{if(!controller.signal.aborted)setResult({value,error:dobError(error)})});return()=>controller.abort();},[value]);
 return <div><p>Date of Birth: {formatDob(value)}</p>{result?.value===value&&result.age!=null?<p>Age: {result.age} years</p>:<p>{result?.value===value?result.error:value?"Calculating age…":"DOB required"}</p>}</div>;
}
