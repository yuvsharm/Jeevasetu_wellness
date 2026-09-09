import {ProtectedPage} from "@/components/auth/protected-page";
import {PractitionerVisitWorkflow} from "@/components/appointments/practitioner-visit-workflow";
export default function Page(){return <ProtectedPage role="PHYSIOTHERAPIST" title="My Appointments"><PractitionerVisitWorkflow/></ProtectedPage>}