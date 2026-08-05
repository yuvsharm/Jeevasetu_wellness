"use client";

export default function ProtectedError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <main className="grid min-h-screen place-items-center px-6"><section className="max-w-lg text-center"><h1 className="text-3xl font-bold text-slate-950">Workspace unavailable</h1><p className="mt-4 text-slate-600">The protected workspace could not be displayed. No internal error details are shown.</p><button onClick={reset} className="mt-7 min-h-12 rounded-xl bg-emerald-700 px-6 font-semibold text-white">Try again</button></section></main>;
}
