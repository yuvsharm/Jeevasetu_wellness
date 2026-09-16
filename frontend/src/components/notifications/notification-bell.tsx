"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import type { Role } from "@/lib/api/contracts";
import { requestJson } from "@/lib/api/client";
import type { NotificationItem, NotificationPage, NotificationSummary } from "@/lib/notifications/contracts";

const POLL_INTERVAL_MS = 45_000;

export function NotificationBell({ role, onSummary }: {
  role: Extract<Role, "OWNER" | "CUSTOMER" | "PHYSIOTHERAPIST">;
  onSummary: (summary: NotificationSummary) => void;
}) {
  const router = useRouter();
  const panelRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [summary, setSummary] = useState<NotificationSummary>({ unread_count: 0, category_counts: {} });
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const query = `role=${encodeURIComponent(role)}`;

  const applySummary = useCallback((value: NotificationSummary) => {
    const safe = {
      unread_count: typeof value?.unread_count === "number" ? value.unread_count : 0,
      category_counts: value?.category_counts ?? {},
    };
    setSummary(safe);
    onSummary(safe);
  }, [onSummary]);

  const refreshCount = useCallback(async () => {
    try {
      applySummary(await requestJson<NotificationSummary>(`/api/notifications/unread-count?${query}`));
    } catch {
      // A background refresh must not interrupt the authenticated workspace.
    }
  }, [applySummary, query]);

  const refreshList = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const page = await requestJson<NotificationPage>(`/api/notifications?${query}`);
      setItems(page.results);
      applySummary(page);
    } catch {
      setError("Notifications could not be loaded. Try again.");
    } finally {
      setLoading(false);
    }
  }, [applySummary, query]);

  useEffect(() => {
    const initial = window.setTimeout(() => void refreshCount(), 0);
    const timer = window.setInterval(refreshCount, POLL_INTERVAL_MS);
    const onFocus = () => void refreshCount();
    window.addEventListener("focus", onFocus);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); window.removeEventListener("focus", onFocus); };
  }, [refreshCount]);

  useEffect(() => {
    if (!open) return;
    const initial = window.setTimeout(() => void refreshList(), 0);
    const close = (event: MouseEvent) => {
      if (!panelRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => { window.clearTimeout(initial); document.removeEventListener("mousedown", close); document.removeEventListener("keydown", escape); };
  }, [open, refreshList]);

  async function openNotification(item: NotificationItem) {
    setError("");
    try {
      if (!item.is_read) {
        await requestJson<NotificationItem>(`/api/notifications/${encodeURIComponent(item.id)}/read?${query}`, { method: "POST" });
        const nextItems = items.map((value) => value.id === item.id ? { ...value, is_read: true } : value);
        setItems(nextItems);
        applySummary({
          unread_count: Math.max(0, summary.unread_count - 1),
          category_counts: {
            ...summary.category_counts,
            [item.category]: Math.max(0, (summary.category_counts[item.category] ?? 0) - 1),
          },
        });
      }
      setOpen(false);
      router.push(item.target_url);
      router.refresh();
    } catch {
      setError("This notification could not be opened. Try again.");
    }
  }

  const badge = summary.unread_count > 99 ? "99+" : String(summary.unread_count);
  return <div className="relative" ref={panelRef}>
    <button
      type="button"
      aria-label={`Notifications, ${summary.unread_count} unread`}
      aria-expanded={open}
      aria-haspopup="dialog"
      onClick={() => setOpen((value) => !value)}
      className="relative flex size-11 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
    >
      <svg aria-hidden="true" viewBox="0 0 24 24" className="size-5 fill-none stroke-current stroke-2"><path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.4-1.4A2 2 0 0 1 18 14.2V11a6 6 0 1 0-12 0v3.2c0 .5-.2 1-.6 1.4L4 17h5m6 0a3 3 0 0 1-6 0" /></svg>
      {summary.unread_count > 0 && <span aria-hidden="true" className="absolute -right-1 -top-1 min-w-5 rounded-full bg-red-600 px-1 text-center text-[11px] font-bold leading-5 text-white">{badge}</span>}
    </button>
    {open && <section role="dialog" aria-label="Notifications" className="fixed inset-x-2 top-20 z-50 max-h-[min(32rem,calc(100vh-6rem))] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:mt-2 sm:w-[min(24rem,calc(100vw-2rem))]">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3"><h2 className="font-bold text-slate-950">Notifications</h2><span className="text-xs font-semibold text-slate-600">{summary.unread_count} unread</span></div>
      <div className="max-h-[min(27rem,calc(100vh-10rem))] overflow-y-auto overscroll-contain">
        {loading && <p role="status" className="p-6 text-center text-sm text-slate-600">Loading notifications…</p>}
        {!loading && error && <div className="p-4 text-sm text-red-700"><p role="alert">{error}</p><button type="button" onClick={() => void refreshList()} className="mt-2 min-h-11 rounded-lg border border-red-200 px-3 font-semibold">Retry</button></div>}
        {!loading && !error && items.length === 0 && <p className="p-8 text-center text-sm text-slate-600">You’re all caught up.</p>}
        {!loading && items.map((item) => <button key={item.id} type="button" onClick={() => void openNotification(item)} className={`block min-h-16 w-full border-b border-slate-100 px-4 py-3 text-left hover:bg-emerald-50 ${item.is_read ? "bg-white text-slate-600" : "bg-emerald-50/60 text-slate-950"}`}>
          <span className="flex items-start gap-2"><span aria-hidden="true" className={`mt-1.5 size-2 shrink-0 rounded-full ${item.is_read ? "bg-slate-300" : "bg-emerald-600"}`} /><span className="min-w-0 flex-1"><span className="block break-words text-sm font-bold">{item.title}</span><span className="mt-1 block break-words text-sm leading-5">{item.message}</span><time aria-label="Notification event time" dateTime={item.created_at} className="mt-1 block text-right text-xs">{new Date(item.created_at).toLocaleString()}</time></span></span>
        </button>)}
      </div>
    </section>}
  </div>;
}
