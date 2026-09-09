"use client";
import {initials} from "@/lib/staff/initials";
import Image from "next/image";
import {useState} from "react";
import type {StaffProfile} from "@/lib/staff/contracts";
export function ProfileAvatar({profile,large=false}:{profile:Pick<StaffProfile,"full_name"|"photo_url"> & {profile_photo?:string};large?:boolean}) {
 const src=profile.photo_url??profile.profile_photo;
 const [failed,setFailed]=useState<string|null>(null);
 return src&&failed!==src?<Image src={src} alt={`${profile.full_name} profile photo`} width={large?128:48} height={large?128:48} unoptimized onError={()=>setFailed(src)} className={`${large?"size-32":"size-12"} shrink-0 rounded-full object-cover`}/>:<span aria-label={`${profile.full_name} avatar`} className={`grid ${large?"size-32 text-4xl":"size-12"} shrink-0 place-items-center rounded-full bg-emerald-100 font-bold`}>{initials(profile.full_name)}</span>;
}
export function leaveDate(value:string) {return new Intl.DateTimeFormat("en-GB",{day:"numeric",month:"short",year:"numeric",timeZone:"UTC"}).format(new Date(`${value}T12:00:00Z`)).replace("Sept", "Sep");}
