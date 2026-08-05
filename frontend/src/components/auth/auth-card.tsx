import type { ReactNode } from "react";

import { Wordmark } from "@/components/brand/wordmark";

export function AuthCard({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <main className="grid min-h-screen place-items-center px-4 py-10 sm:px-6">
      <section className="w-full max-w-lg rounded-3xl border border-slate-200 bg-white p-6 shadow-xl shadow-emerald-950/5 sm:p-10" aria-labelledby="auth-title">
        <Wordmark />
        <div className="mt-8">
          <h1 id="auth-title" className="text-3xl font-bold tracking-tight text-slate-950">{title}</h1>
          <p className="mt-2 leading-7 text-slate-600">{description}</p>
        </div>
        <div className="mt-8">{children}</div>
      </section>
    </main>
  );
}
