"use client";
import {useState} from "react";
import {useMutation,useQueryClient} from "@tanstack/react-query";
import {DobField,formatDob,dobError} from "./dob-field";
import {requestJson} from "@/lib/api/client";
export function DobEditor({dob,age,url}:{dob:string|null|undefined;age:number|null|undefined;url:string}){
 const [editing,setEditing]=useState(false),[value,setValue]=useState(dob??"");const client=useQueryClient();
 const save=useMutation({mutationFn:()=>requestJson(url,{method:"PATCH",body:JSON.stringify({date_of_birth:value})}),onSuccess:()=>{setEditing(false);client.invalidateQueries({queryKey:["staff"]});client.invalidateQueries({queryKey:["staff-me"]});client.invalidateQueries({queryKey:["therapist-availability-profile"]});client.invalidateQueries({queryKey:["public-practitioners"]});client.invalidateQueries({queryKey:["my-practitioner-applications"]})}});
 return <div className="mt-3"><p>Date of Birth: {formatDob(dob)}</p><p>{age!=null?`Age: ${age} years`:"DOB required"}</p>{editing?<form onSubmit={e=>{e.preventDefault();save.mutate()}} className="mt-3 grid gap-3"><DobField value={value} onChange={setValue}/>{save.isError&&<p role="alert" className="text-red-700">{dobError(save.error)}</p>}<div className="flex gap-2"><button disabled={save.isPending} className="button-primary">Save Date of Birth</button><button type="button" onClick={()=>setEditing(false)} className="button-secondary">Cancel</button></div></form>:<button type="button" onClick={()=>{setValue(dob??"");setEditing(true);save.reset()}} className="mt-2 font-bold text-emerald-800">Edit Date of Birth</button>}</div>;
}
