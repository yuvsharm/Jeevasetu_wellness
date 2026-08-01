export default function Home() {
  return (
    <main className="flex min-h-screen items-center justify-center px-6 py-16">
      <section
        className="w-full max-w-3xl rounded-3xl border border-emerald-100 bg-white p-8 shadow-sm sm:p-12"
        aria-labelledby="page-title"
      >
        <p className="mb-4 font-semibold tracking-wide text-emerald-700 uppercase">
          Jeevasetu Wellness
        </p>
        <h1 id="page-title" className="text-4xl font-bold tracking-tight text-slate-950 sm:text-5xl">
          Professional physiotherapy care, thoughtfully delivered at home.
        </h1>
        <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-700">
          Our platform foundation is being prepared with accessibility, privacy, and reliable care
          delivery at its core.
        </p>
        <aside className="mt-8 rounded-2xl bg-emerald-50 p-5 text-emerald-950" aria-label="Project status">
          <p className="font-medium">Phase 1A: development foundation</p>
          <p className="mt-1 text-sm leading-6">Service booking is not available yet.</p>
        </aside>
      </section>
    </main>
  );
}

