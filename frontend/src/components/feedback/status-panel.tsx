import type { ReactNode } from "react";

export function StatusPanel({ tone = "info", children }: { tone?: "info" | "error" | "success"; children: ReactNode }) {
  const styles = {
    info: "border-sky-200 bg-sky-50 text-sky-950",
    error: "border-red-200 bg-red-50 text-red-950",
    success: "border-emerald-200 bg-emerald-50 text-emerald-950",
  }[tone];
  return <div role={tone === "error" ? "alert" : "status"} className={`rounded-xl border p-4 text-sm ${styles}`}>{children}</div>;
}

export function LoadingState({ label = "Loading your secure workspace…" }: { label?: string }) {
  return (
    <div className="grid min-h-64 place-items-center" role="status" aria-live="polite">
      <div className="text-center">
        <span className="mx-auto block size-9 animate-spin rounded-full border-4 border-emerald-100 border-t-emerald-700 motion-reduce:animate-none" aria-hidden="true" />
        <p className="mt-4 font-medium text-slate-700">{label}</p>
      </div>
    </div>
  );
}
