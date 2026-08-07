import {PublicShell} from "@/components/public/public-shell";
import {PageHero} from "@/components/public/page-hero";
import {PublicPractitionerDirectory} from "@/components/practitioners/public-directory";
export default function PractitionersPage(){return <PublicShell><main><PageHero eyebrow="JeevaSetu verified" title="Meet our practitioners">Browse safe, verified professional profiles. Private contact details, documents, schedules and customer information are never published.</PageHero><section className="section pt-0"><div className="site-container"><PublicPractitionerDirectory/></div></section></main></PublicShell>}

