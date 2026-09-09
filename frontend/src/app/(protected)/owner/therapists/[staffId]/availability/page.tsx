import {ProtectedPage} from "@/components/auth/protected-page";
import {TherapistAvailabilityPage} from "@/components/availability/therapist-availability-page";

export default async function Page({params}:{params:Promise<{staffId:string}>}){return <ProtectedPage role="OWNER" title="Therapist availability"><TherapistAvailabilityPage staffId={(await params).staffId}/></ProtectedPage>}
