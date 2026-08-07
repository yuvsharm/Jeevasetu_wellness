import {ProtectedPage} from "@/components/auth/protected-page";
import {EnrollmentForm} from "@/components/practitioners/enrollment-form";
import {PractitionerProfilePhotoUpload} from "@/components/practitioners/profile-photo-upload";
export default function PractitionerApplicationPage(){return <ProtectedPage role="CUSTOMER" title="Practitioner enrollment"><EnrollmentForm/><PractitionerProfilePhotoUpload/></ProtectedPage>}
