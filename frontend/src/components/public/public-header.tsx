"use client";

import Link from "next/link";
import { useState } from "react";

import { Wordmark } from "@/components/brand/wordmark";

const links = [
  ["About", "/about"], ["Therapies", "/therapies"], ["Packages", "/packages"],
  ["Practitioners", "/practitioners"], ["Why us", "/why-choose-us"], ["Gallery", "/gallery"], ["FAQ", "/faq"], ["Contact", "/contact"],
] as const;

export function PublicHeader() {
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-50 border-b border-[#0b6b3a]/10 bg-[#fffdf8]/95 backdrop-blur-xl">
      <div className="site-container flex min-h-20 items-center justify-between gap-6">
        <Wordmark publicSite />
        <nav className="hidden items-center gap-6 lg:flex" aria-label="Primary navigation">
          {links.map(([label, href]) => <Link key={href} href={href} className="nav-link">{label}</Link>)}
        </nav>
        <div className="hidden items-center gap-3 sm:flex">
          <Link href="/login" className="nav-link">Sign in</Link>
          <Link href="/work-with-us" className="nav-link">Work with us</Link><Link href="/book-appointment" className="button-primary">Book appointment</Link>
        </div>
        <button className="grid size-11 place-items-center rounded-full border border-[#0b6b3a]/20 lg:hidden" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls="mobile-navigation" aria-label="Toggle navigation">
          <span aria-hidden="true" className="text-xl">{open ? "×" : "☰"}</span>
        </button>
      </div>
      {open && <nav id="mobile-navigation" className="site-container grid gap-1 border-t border-[#0b6b3a]/10 py-4 lg:hidden" aria-label="Mobile navigation">
        {links.map(([label, href]) => <Link key={href} href={href} onClick={() => setOpen(false)} className="rounded-xl px-3 py-3 font-medium text-[#163c2a] hover:bg-[#edf7ef]">{label}</Link>)}
        <Link href="/login" className="rounded-xl px-3 py-3 font-medium text-[#163c2a]">Sign in</Link>
        <Link href="/work-with-us" className="rounded-xl px-3 py-3 font-medium text-[#163c2a]">Work with JeevaSetu</Link><Link href="/book-appointment" className="button-primary mt-2 text-center">Book appointment</Link>
      </nav>}
    </header>
  );
}
