"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { Wordmark } from "@/components/brand/wordmark";
import { isActivePublicRoute, publicNavigation } from "@/lib/public-site/navigation";

export function PublicHeader() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  return <header className="public-header sticky top-0 z-50 border-b border-[#0b6b3a]/10 bg-[#fffdf8]/90 backdrop-blur-xl">
    <div className="site-container flex min-h-[4.75rem] items-center justify-between gap-4"><Wordmark publicSite /><nav className="hidden items-center gap-1 xl:flex" aria-label="Primary navigation">{publicNavigation.map(({ label, href }) => <Link key={`${label}-${href}`} href={href} aria-current={isActivePublicRoute(pathname, href) ? "page" : undefined} className="nav-link">{label}</Link>)}</nav><div className="hidden items-center gap-2 md:flex"><Link href="/login" className="nav-link">Sign in</Link><Link href="/work-with-us" className="button-secondary !min-h-11 !px-4">Work with us</Link><Link href="/book-appointment" className="button-primary !min-h-11 !px-4">Book appointment</Link></div><button className="grid size-11 place-items-center rounded-full border border-[#0b6b3a]/20 bg-white/70 xl:hidden" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls="mobile-navigation" aria-label="Toggle navigation"><span aria-hidden="true" className="text-xl">{open ? "×" : "☰"}</span></button></div>
    {open && <nav id="mobile-navigation" className="site-container grid max-h-[calc(100vh-5rem)] gap-1 overflow-y-auto border-t border-[#0b6b3a]/10 py-4 xl:hidden" aria-label="Mobile navigation">{publicNavigation.map(({ label, href }) => <Link key={`${label}-${href}`} href={href} aria-current={isActivePublicRoute(pathname, href) ? "page" : undefined} onClick={() => setOpen(false)} className="mobile-nav-link">{label}</Link>)}<div className="mt-3 grid gap-2 border-t border-[#0b6b3a]/10 pt-4 sm:grid-cols-3"><Link href="/login" onClick={() => setOpen(false)} className="button-secondary">Sign in</Link><Link href="/work-with-us" onClick={() => setOpen(false)} className="button-secondary">Work with us</Link><Link href="/book-appointment" onClick={() => setOpen(false)} className="button-primary">Book appointment</Link></div></nav>}
  </header>;
}