import { Suspense } from "react";
import { AuthCard } from "@/components/auth/auth-card";
import { PractitionerLogin } from "@/components/auth/practitioner-auth";

export default function TherapistLoginPage(){return <AuthCard title="Therapist sign in" description="Use your registered mobile number and password to continue your JeevaSetu application or open your practitioner dashboard."><Suspense fallback={null}><PractitionerLogin/></Suspense></AuthCard>}
