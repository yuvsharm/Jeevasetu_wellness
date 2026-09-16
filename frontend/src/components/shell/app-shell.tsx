"use client";

import {ProfileAvatar} from "@/components/staff/profile-avatar";
import { NotificationBell } from "@/components/notifications/notification-bell";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type MouseEvent, type ReactNode } from "react";

import { Wordmark } from "@/components/brand/wordmark";
import type { Role, Session } from "@/lib/api/contracts";
import { requestJson } from "@/lib/api/client";
import { sessionEndpoints } from "@/lib/api/endpoints";
import { roleLabels } from "@/lib/auth/roles";
import { roleNavigation } from "@/lib/navigation/role-navigation";
import type { NotificationCategory, NotificationSummary } from "@/lib/notifications/contracts";

export function AppShell({ session, role, title, children }: { session: Session; role: Role; title: string; children: ReactNode }) {
  const [accountProfile, setAccountProfile] = useState<{full_name:string;photo_url:string}|null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [activeHash, setActiveHash] = useState("");
  const [notificationSummary, setNotificationSummary] = useState<NotificationSummary>({ unread_count: 0, category_counts: {} });
  const pathname = usePathname();
  const router = useRouter();
  const displayName = `${session.user.first_name} ${session.user.last_name}`.trim() || "JeevaSetu user";
  useEffect(() => {
    if (role !== "PHYSIOTHERAPIST" && role !== "CUSTOMER") return;
    let live = true;
    requestJson<{full_name:string;photo_url:string}>(role === "PHYSIOTHERAPIST" ? "/api/staff/me" : "/api/customer/profile")
      .then((value) => { if (live && typeof value?.full_name === "string") setAccountProfile(value); })
      .catch(() => undefined);
    return () => { live = false; };
  }, [role]);
  useEffect(() => {
    const sync = () => {
      const hash = window.location.hash;
      setActiveHash(hash);
      const target = hash ? document.getElementById(hash.slice(1)) : null;
      if (!target) return;
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      const focusTarget = target.querySelector<HTMLElement>("h1, h2, h3") ?? target;
      if (!focusTarget.hasAttribute("tabindex")) focusTarget.setAttribute("tabindex", "-1");
      focusTarget.focus({ preventScroll: true });
    };
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  function navigateToSection(event: MouseEvent<HTMLAnchorElement>, href: string) {
    const [targetPath, hash] = href.split("#");
    if (!hash || targetPath !== pathname) return;
    const target = document.getElementById(hash);
    if (!target) return;
    event.preventDefault();
    window.history.replaceState(null, "", `#${hash}`);
    setActiveHash(`#${hash}`);
    target.scrollIntoView({ behavior: "smooth", block: "start" });
    const focusTarget = target.querySelector<HTMLElement>("h1, h2, h3") ?? target;
    if (!focusTarget.hasAttribute("tabindex")) focusTarget.setAttribute("tabindex", "-1");
    focusTarget.focus({ preventScroll: true });
    setMobileOpen(false);
  }
  async function logout() {
    setLoggingOut(true);
    try { await requestJson(sessionEndpoints.logout, { method: "POST" }); }
    finally { router.replace(role === "CUSTOMER" ? "/customer-login" : "/login"); router.refresh(); }
  }
  const updateNotificationSummary = useCallback((value: NotificationSummary) => setNotificationSummary(value), []);
  function navigationBadge(label: string) {
    const categories: Partial<Record<string, NotificationCategory>> = {
      "Appointment Requests": "APPOINTMENTS",
      "Practitioner Applications": "PRACTITIONERS",
      "Customer Reviews": "REVIEWS",
    };
    const category = categories[label];
    if (role === "OWNER" && category) return notificationSummary.category_counts[category] ?? 0;
    if ((role === "CUSTOMER" || role === "PHYSIOTHERAPIST") && label === "My Appointments") {
      return notificationSummary.category_counts.APPOINTMENTS ?? 0;
    }
    return 0;
  }
  const navigation = <nav aria-label={`${roleLabels[role]} navigation`} className="mt-6 space-y-1">{roleNavigation[role].map((item) => { const [itemPath, itemHash=""] = item.href?.split("#") ?? []; const active = item.href ? pathname === itemPath && (itemHash ? activeHash === `#${itemHash}` : !activeHash) : false; const unread = navigationBadge(item.label); return item.href ? <Link key={item.label} href={item.href} onClick={(event) => navigateToSection(event, item.href!)} aria-current={active ? "location" : undefined} className={`flex min-h-11 items-center justify-between gap-2 rounded-xl px-3 text-sm font-semibold ${active ? "bg-emerald-100 text-emerald-950" : "text-slate-700 hover:bg-slate-100"}`}><span>{item.label}</span>{unread > 0 && <span aria-label={`${unread} unread`} className="min-w-5 rounded-full bg-emerald-700 px-1.5 text-center text-[11px] leading-5 text-white">{unread > 99 ? "99+" : unread}</span>}</Link> : <span key={item.label} aria-disabled="true" title="Coming in a future phase" className="flex min-h-11 cursor-not-allowed items-center justify-between rounded-xl px-3 text-sm text-slate-400"><span>{item.label}</span><span className="text-[10px] font-bold uppercase">Later</span></span>; })}</nav>;
  return (
    <div className="min-h-screen bg-slate-50">
      <aside className={`fixed inset-y-0 left-0 z-30 hidden overflow-y-auto border-r border-slate-200 bg-white p-4 transition-[width] lg:block ${collapsed ? "w-20" : "w-72"}`}><Wordmark compact={collapsed} /><button className="mt-6 min-h-11 w-full rounded-xl border border-slate-200 text-sm font-semibold" onClick={() => setCollapsed((value) => !value)} aria-expanded={!collapsed}>{collapsed ? "Expand" : "Collapse sidebar"}</button>{!collapsed && navigation}</aside>
      {mobileOpen && <div className="fixed inset-0 z-40 bg-slate-950/40 lg:hidden" onClick={() => setMobileOpen(false)}><aside className="h-full w-[min(20rem,90vw)] bg-white p-5" onClick={(event) => event.stopPropagation()}><div className="flex items-center justify-between"><Wordmark /><button className="min-h-11 rounded-lg px-3 font-semibold" onClick={() => setMobileOpen(false)} aria-label="Close navigation">Close</button></div>{navigation}</aside></div>}
      <div className={collapsed ? "lg:pl-20" : "lg:pl-72"}>
        <header className="sticky top-0 z-20 flex min-h-18 items-center justify-between gap-2 border-b border-slate-200 bg-white/95 px-2 backdrop-blur sm:px-6"><div className="flex min-w-0 items-center gap-2 sm:gap-3"><button className="min-h-11 shrink-0 rounded-xl border border-slate-200 px-3 font-semibold lg:hidden" onClick={() => setMobileOpen(true)} aria-expanded={mobileOpen}>Menu</button><div className="min-w-0"><p className="truncate text-xs font-bold tracking-wide text-emerald-700 uppercase">{roleLabels[role]}</p><h1 className="truncate text-base font-bold text-slate-950 sm:text-xl">{title}</h1></div></div><div className="flex shrink-0 items-center gap-2">{(role==="OWNER"||role==="CUSTOMER"||role==="PHYSIOTHERAPIST")&&<NotificationBell role={role} onSummary={updateNotificationSummary}/>}<div className="relative"><button aria-label={`Open profile menu for ${displayName}`} className="flex min-h-11 items-center gap-2 rounded-xl border border-slate-200 px-2 text-left sm:px-3" onClick={() => setProfileOpen((value) => !value)} aria-expanded={profileOpen} aria-haspopup="menu">{(role==="PHYSIOTHERAPIST"||role==="CUSTOMER")&&<ProfileAvatar profile={accountProfile??{full_name:displayName,photo_url:""}}/>}<span className="hidden text-sm font-semibold text-slate-900 md:block">{displayName}</span></button>{profileOpen && <div role="menu" className="absolute right-0 mt-2 w-56 rounded-xl border border-slate-200 bg-white p-2 shadow-xl"><Link role="menuitem" href="/profile" className="block min-h-11 rounded-lg px-3 py-3 text-sm font-semibold hover:bg-slate-100">Profile</Link><button role="menuitem" className="min-h-11 w-full rounded-lg px-3 text-left text-sm font-semibold text-red-700 hover:bg-red-50" onClick={logout} disabled={loggingOut}>{loggingOut ? "Signing out…" : "Sign out"}</button></div>}</div></div></header>
        <main className="p-4 sm:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
