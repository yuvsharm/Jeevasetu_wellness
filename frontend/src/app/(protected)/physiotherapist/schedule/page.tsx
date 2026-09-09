import {ProtectedPage} from "@/components/auth/protected-page";
import {SelfSchedule} from "@/components/practitioners/self-schedule";
export default function Page(){return <ProtectedPage role="PHYSIOTHERAPIST" title="My Schedule / Time Off"><SelfSchedule/></ProtectedPage>}