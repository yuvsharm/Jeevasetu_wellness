import {ProtectedPage} from "@/components/auth/protected-page";
import {LearningCentre} from "@/components/practitioners/learning-centre";
export default function Page(){return <ProtectedPage role="OWNER" title="Learning Content"><LearningCentre owner={true}/></ProtectedPage>}
