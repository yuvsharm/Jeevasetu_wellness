"use client";
import {useQuery} from "@tanstack/react-query";
import {requestJson} from "@/lib/api/client";
import {TherapistAvailabilityPage} from "@/components/availability/therapist-availability-page";
export function SelfSchedule(){const q=useQuery({queryKey:["staff-me"],queryFn:()=>requestJson<{id:string}>("/api/staff/me")});return q.data?<TherapistAvailabilityPage staffId={q.data.id} self/>:<p>{q.isError?"Schedule could not be loaded.":"Loading your schedule…"}</p>}
