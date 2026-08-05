import Link from "next/link";

export default function NotFound() {
  return <main className="grid min-h-screen place-items-center px-6 text-center"><section><p className="text-sm font-bold tracking-widest text-emerald-700 uppercase">404</p><h1 className="mt-3 text-4xl font-bold text-slate-950">Page not found</h1><p className="mt-4 text-slate-600">The requested page is unavailable.</p><Link href="/dashboard" className="mt-8 inline-flex min-h-12 items-center rounded-xl bg-emerald-700 px-6 font-semibold text-white">Go to dashboard</Link></section></main>;
}
