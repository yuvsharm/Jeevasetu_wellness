"use client";
import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query";
import {requestJson} from "@/lib/api/client";

type WorkState = {is_open_to_work:boolean};
const key = ["open-to-work"];
export function OpenToWorkControl(){
 const client=useQueryClient();
 const state=useQuery({queryKey:key,queryFn:()=>requestJson<WorkState>("/api/practitioners/open-to-work")});
 const update=useMutation({mutationFn:(enabled:boolean)=>requestJson<WorkState>("/api/practitioners/open-to-work",{method:"POST",body:JSON.stringify({enabled})}),onSuccess:data=>client.setQueryData(key,data)});
 const enabled=state.data?.is_open_to_work??false;
 return <section className="mt-6 flex flex-wrap items-center justify-between gap-4 rounded-2xl border bg-white p-5"><div><h2 className="text-xl font-bold">Open to Work</h2><p className="mt-1 text-sm text-slate-600">{state.isPending?"Loading work preference…":enabled?"Available for new eligible assignments.":"Not accepting new assignments. Existing visits remain active."}</p></div><button role="switch" aria-label="Open to Work" aria-checked={enabled} disabled={!state.data||update.isPending} onClick={()=>update.mutate(!enabled)} className={`min-h-12 rounded-full px-6 font-bold text-white disabled:opacity-50 ${enabled?"bg-emerald-700":"bg-slate-600"}`}>{enabled?"On":"Off"}</button>{(update.error||state.error)&&<p role="alert" className="w-full text-sm text-red-700">{(update.error||state.error)?.message}</p>}</section>;
}
