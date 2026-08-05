import Link from "next/link";

import { Wordmark } from "@/components/brand/wordmark";

export default function UnauthorizedPage() {
  return <main className="grid min-h-screen place-items-center px-6"><section className="max-w-xl text-center"><Wordmark /><p className="mt-10 text-sm font-bold tracking-widest text-amber-700 uppercase">Access unavailable</p><h1 className="mt-3 text-4xl font-bold text-slate-950">This workspace is not available for your active role.</h1><p className="mt-4 leading-7 text-slate-600">Confirm your organization context or ask an authorized administrator to review your active membership and role.</p><Link href="/dashboard" className="mt-8 inline-flex min-h-12 items-center rounded-xl bg-emerald-700 px-6 font-semibold text-white">Return to dashboard</Link></section></main>;
}
