import {ProtectedPage} from "@/components/auth/protected-page";
import {PractitionerIdentity} from "@/components/practitioners/my-profile";
import {OpenToWorkControl} from "@/components/practitioners/open-to-work";
import {PractitionerDashboardOverview} from "@/components/practitioners/practitioner-dashboard";
import {PractitionerReviews} from "@/components/appointments/review-panels";
export default function PhysiotherapistPage(){return <ProtectedPage role="PHYSIOTHERAPIST" title="Dashboard"><PractitionerIdentity/><OpenToWorkControl/><PractitionerDashboardOverview/><PractitionerReviews/></ProtectedPage>}
