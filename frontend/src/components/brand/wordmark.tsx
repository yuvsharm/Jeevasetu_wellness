import Link from "next/link";

export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className="inline-flex items-center gap-3 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-emerald-700">
      <span className="grid size-10 place-items-center rounded-xl bg-emerald-700 font-bold text-white" aria-hidden="true">
        JS
      </span>
      {!compact && (
        <span>
          <span className="block font-bold tracking-tight text-slate-950">JeevaSetu Wellness</span>
          <span className="block text-xs text-slate-600">Professional home care</span>
        </span>
      )}
      <span className="sr-only">JeevaSetu Wellness home</span>
    </Link>
  );
}
