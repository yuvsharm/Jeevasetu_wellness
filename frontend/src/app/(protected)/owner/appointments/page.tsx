import {ScheduleOperations} from "@/components/appointments/operational-schedule";
import {ProtectedPage} from "@/components/auth/protected-page";

export default function OwnerAppointmentSchedulePage(){
 return <ProtectedPage role="OWNER" title="Appointment Schedule"><ScheduleOperations/></ProtectedPage>;
}
