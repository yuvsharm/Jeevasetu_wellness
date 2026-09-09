import {ProtectedPage} from "@/components/auth/protected-page";
import {LearningGuidePage} from "@/components/practitioners/learning-centre";
export default async function Page({params}:{params:Promise<{id:string}>}){const {id}=await params;return <ProtectedPage role="PHYSIOTHERAPIST" title="Learning Guide"><LearningGuidePage id={id} owner={false}/></ProtectedPage>}
