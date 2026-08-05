"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";

import { Wordmark } from "@/components/brand/wordmark";
import type { Role, Session } from "@/lib/api/contracts";
import { requestJson } from "@/lib/api/client";
import { sessionEndpoints } from "@/lib/api/endpoints";
import { roleLabels } from "@/lib/auth/roles";
import { roleNavigation } from "@/lib/navigation/role-navigation";

export function AppShell({ session, role, title, children }: { session: Session; role: Role; title: string; children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const pathname = usePathname();
  const router = useRouter();
  const displayName = `${session.user.first_name} ${session.user.last_name}`.trim() || "JeevaSetu user";
  async function logout() {
    setLoggingOut(true);
    try { await requestJson(sessionEndpoints.logout, { method: "POST" }); }
    finally { router.replace("/login"); router.refresh(); }
  }
  const navigation = <nav aria-label={`${roleLabels[role]} navigation`} className="mt-6 space-y-1">{roleNavigation[role].map((item) => item.href ? <Link key={item.label} href={item.href} onClick={() => setMobileOpen(false)} aria-current={pathname === item.href ? "page" : undefined} className={`flex min-h-11 items-center rounded-xl px-3 text-sm font-semibold ${pathname === item.href ? "bg-emerald-100 text-emerald-950" : "text-slate-700 hover:bg-slate-100"}`}>{item.label}</Link> : <span key={item.label} aria-disabled="true" title="Coming in a future phase" className="flex min-h-11 cursor-not-allowed items-center justify-between rounded-xl px-3 text-sm text-slate-400"><span>{item.label}</span><span className="text-[10px] font-bold uppercase">Later</span></span>)}</nav>;
  return (
    <div className="min-h-screen bg-slate-50">
      <aside className={`fixed inset-y-0 left-0 z-30 hidden border-r border-slate-200 bg-white p-4 transition-[width] lg:block ${collapsed ? "w-20" : "w-72"}`}><Wordmark compact={collapsed} /><button className="mt-6 min-h-11 w-full rounded-xl border border-slate-200 text-sm font-semibold" onClick={() => setCollapsed((value) => !value)} aria-expanded={!collapsed}>{collapsed ? "Expand" : "Collapse sidebar"}</button>{!collapsed && navigation}</aside>
      {mobileOpen && <div className="fixed inset-0 z-40 bg-slate-950/40 lg:hidden" onClick={() => setMobileOpen(false)}><aside className="h-full w-[min(20rem,90vw)] bg-white p-5" onClick={(event) => event.stopPropagation()}><div className="flex items-center justify-between"><Wordmark /><button className="min-h-11 rounded-lg px-3 font-semibold" onClick={() => setMobileOpen(false)} aria-label="Close navigation">Close</button></div>{navigation}</aside></div>}
      <div className={collapsed ? "lg:pl-20" : "lg:pl-72"}>
        <header className="sticky top-0 z-20 flex min-h-18 items-center justify-between border-b border-slate-200 bg-white/95 px-4 backdrop-blur sm:px-6"><div className="flex items-center gap-3"><button className="min-h-11 rounded-xl border border-slate-200 px-4 font-semibold lg:hidden" onClick={() => setMobileOpen(true)} aria-expanded={mobileOpen}>Menu</button><div><p className="text-xs font-bold tracking-wide text-emerald-700 uppercase">{roleLabels[role]}</p><h1 className="text-xl font-bold text-slate-950">{title}</h1></div></div><div className="flex items-center gap-2"><button disabled title="Notifications are not implemented yet" aria-label="Notifications unavailable" className="min-h-11 cursor-not-allowed rounded-xl border border-slate-200 px-3 text-sm text-slate-400">Alerts</button><div className="relative"><button className="min-h-11 rounded-xl border border-slate-200 px-4 text-left" onClick={() => setProfileOpen((value) => !value)} aria-expanded={profileOpen} aria-haspopup="menu"><span className="block text-sm font-semibold text-slate-900">{displayName}</span><span className="block text-xs text-slate-500">{session.access.organization.slug}</span></button>{profileOpen && <div role="menu" className="absolute right-0 mt-2 w-56 rounded-xl border border-slate-200 bg-white p-2 shadow-xl"><Link role="menuitem" href="/profile" className="block min-h-11 rounded-lg px-3 py-3 text-sm font-semibold hover:bg-slate-100">Profile</Link><button role="menuitem" className="min-h-11 w-full rounded-lg px-3 text-left text-sm font-semibold text-red-700 hover:bg-red-50" onClick={logout} disabled={loggingOut}>{loggingOut ? "Signing out…" : "Sign out"}</button></div>}</div></div></header>
        <main className="p-4 sm:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
