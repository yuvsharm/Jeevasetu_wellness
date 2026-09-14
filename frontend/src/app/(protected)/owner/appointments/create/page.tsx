import {OfflineAppointmentBooking} from "@/components/appointments/offline-appointment-booking";
import {ProtectedPage} from "@/components/auth/protected-page";

export default function OwnerCreateAppointmentPage(){
 return <ProtectedPage role="OWNER" title="Book for Customer"><OfflineAppointmentBooking/></ProtectedPage>;
}
