import {CustomerAppointmentDetail} from "@/components/appointments/customer-dashboard";
import {ProtectedPage} from "@/components/auth/protected-page";

export default async function CustomerAppointmentPage({params}:{params:Promise<{id:string}>}){const {id}=await params;return <ProtectedPage role="CUSTOMER" title="Appointment Details"><CustomerAppointmentDetail requestId={id}/></ProtectedPage>}
