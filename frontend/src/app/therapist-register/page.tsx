import { Wordmark } from "@/components/brand/wordmark";
import { PractitionerRegistration } from "@/components/auth/practitioner-auth";

export default function TherapistRegisterPage(){return <main className="min-h-screen bg-[#f8f7f1] px-4 py-8 sm:py-12"><div className="mx-auto max-w-5xl"><Wordmark/><p className="mt-8 text-sm font-bold uppercase tracking-widest text-emerald-700">Your next professional chapter</p><h1 className="mt-3 font-serif text-4xl text-emerald-950">Apply to join NuriPain Ease</h1><p className="mt-4 max-w-2xl text-slate-600">Share your professional details, verify your mobile and review your complete application. Your profile becomes operational only after approval.</p><PractitionerRegistration/></div></main>}
