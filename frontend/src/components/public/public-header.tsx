"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { BookingLink } from "@/components/auth/booking-link";
import { useOptionalSession } from "@/components/auth/session-provider";
import { Wordmark } from "@/components/brand/wordmark";
import { requestJson } from "@/lib/api/client";
import { sessionEndpoints } from "@/lib/api/endpoints";
import { activeRoles } from "@/lib/auth/roles";
import { isActivePublicRoute, publicNavigation } from "@/lib/public-site/navigation";

export function PublicHeader() {
  const [open, setOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const pathname = usePathname();
  const session = useOptionalSession();
  const roles = session?.data ? activeRoles(session.data.access.roles) : [];
  const customer = roles.includes("CUSTOMER");

  async function logout() {
    setLoggingOut(true);
    try { await requestJson(sessionEndpoints.logout, { method: "POST" }); }
    finally { await session?.refetch(); window.location.assign("/"); setLoggingOut(false); }
  }

  return <header className="public-header sticky top-0 z-50 border-b border-[#0b6b3a]/10 bg-[#fffdf8]/92 backdrop-blur-xl">
    <div className="site-container flex min-h-[4.75rem] items-center justify-between gap-2 sm:gap-3">
      <Wordmark publicSite />
      <nav className="hidden items-center 2xl:flex" aria-label="Primary navigation">{publicNavigation.map(({ label, href }) => <Link key={`${label}-${href}`} href={href} aria-current={isActivePublicRoute(pathname, href) ? "page" : undefined} className="nav-link whitespace-nowrap">{label}</Link>)}</nav>
      <div className="hidden items-center gap-1 sm:flex">
        <Link href="/login" className="nav-link whitespace-nowrap text-[#5b6c63]">Staff Login</Link>
        {customer ? <><Link href="/customer" className="nav-link whitespace-nowrap">Customer Dashboard</Link><button onClick={logout} disabled={loggingOut} className="nav-link whitespace-nowrap">{loggingOut ? "Signing out…" : "Logout"}</button></> : <><Link href="/customer-login" className="nav-link whitespace-nowrap">Customer Login</Link><Link href="/customer-register" className="nav-link whitespace-nowrap">Customer Register</Link></>}
        <BookingLink href="/book-appointment" className="button-primary !min-h-11 !px-4 whitespace-nowrap">Book Appointment</BookingLink>
      </div>
      <nav aria-label="Customer access" className="ml-auto flex min-w-0 items-center gap-1 sm:hidden">
        {customer
          ? <Link href="/customer" className="inline-flex min-h-10 items-center rounded-full px-2.5 text-xs font-bold text-[#0b6b3a] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Account</Link>
          : <><Link href="/customer-login" className="inline-flex min-h-10 items-center rounded-full px-2 text-xs font-bold text-[#0b6b3a] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Login</Link><Link href="/customer-register" className="inline-flex min-h-10 items-center rounded-full border border-[#0b6b3a]/25 bg-[#edf7ef] px-2.5 text-xs font-bold text-[#0b6b3a] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Register</Link></>}
      </nav>
      <button className="grid size-11 shrink-0 place-items-center rounded-full border border-[#0b6b3a]/20 bg-white/80 2xl:hidden" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls="mobile-navigation" aria-label="Toggle navigation"><span aria-hidden="true" className="text-xl">{open ? "×" : "☰"}</span></button>
    </div>
    {open && <nav id="mobile-navigation" className="site-container grid max-h-[calc(100vh-5rem)] gap-1 overflow-y-auto border-t border-[#0b6b3a]/10 py-4 2xl:hidden" aria-label="Mobile navigation">
      {publicNavigation.map(({ label, href }) => <Link key={`${label}-${href}`} href={href} aria-current={isActivePublicRoute(pathname, href) ? "page" : undefined} onClick={() => setOpen(false)} className="mobile-nav-link">{label}</Link>)}
      <Link href="/login" onClick={() => setOpen(false)} className="mobile-nav-link">Staff Login</Link>
      {customer ? <><Link href="/customer" onClick={() => setOpen(false)} className="mobile-nav-link">Customer Dashboard</Link><button onClick={logout} className="mobile-nav-link text-left">Logout</button></> : <><Link href="/customer-login" onClick={() => setOpen(false)} className="mobile-nav-link">Customer Login</Link><Link href="/customer-register" onClick={() => setOpen(false)} className="mobile-nav-link">Customer Register</Link></>}
      <BookingLink href="/book-appointment" onClick={() => setOpen(false)} className="button-primary mt-3">Book Appointment</BookingLink>
    </nav>}
  </header>;
}
