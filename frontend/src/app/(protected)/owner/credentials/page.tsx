import {ProtectedPage} from "@/components/auth/protected-page";
import {CredentialReviews} from "@/components/practitioners/credential-reviews";
export default function Page(){return <ProtectedPage role="OWNER" title="Credential Reviews"><CredentialReviews/></ProtectedPage>}
