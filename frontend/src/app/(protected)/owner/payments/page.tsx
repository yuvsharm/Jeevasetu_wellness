import {PaymentOperations} from "@/components/appointments/payment-operations";
import {ProtectedPage} from "@/components/auth/protected-page";

export default function OwnerPaymentsPage(){
 return <ProtectedPage role="OWNER" title="Appointment Payments"><PaymentOperations/></ProtectedPage>;
}
