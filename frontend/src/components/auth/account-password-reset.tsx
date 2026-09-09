"use client";
import {useSearchParams} from "next/navigation";
import {CustomerPasswordReset} from "./customer-password-reset";
export function AccountPasswordReset(){const search=useSearchParams();return <CustomerPasswordReset context={search.get("context")==="therapist"?"therapist":"staff"}/>}
