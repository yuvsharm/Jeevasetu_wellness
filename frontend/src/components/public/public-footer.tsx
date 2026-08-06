import Link from "next/link";

import { Wordmark } from "@/components/brand/wordmark";
import { contact } from "@/lib/public-site/content";

export function PublicFooter() {
  return <footer className="bg-[#073d25] text-white">
    <div className="site-container grid gap-10 py-14 md:grid-cols-3">
      <div><Wordmark inverted publicSite /><p className="mt-5 max-w-sm text-sm leading-7 text-white/70">Thoughtful Ayurvedic wellness services, brought to the comfort of your home in Meerut.</p></div>
      <div><h2 className="footer-heading">Quick links</h2><div className="mt-4 grid grid-cols-2 gap-3 text-sm text-white/75"><Link href="/about">About us</Link><Link href="/therapies">Therapies</Link><Link href="/packages">Packages</Link><Link href="/faq">FAQ</Link><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link></div></div>
      <div><h2 className="footer-heading">Contact</h2><address className="mt-4 space-y-2 text-sm not-italic leading-7 text-white/75"><a href={contact.phoneHref}>{contact.phone}</a><br/><a href={`mailto:${contact.email}`}>{contact.email}</a><p>{contact.address}</p><p aria-label="Social media coming soon">Instagram · Facebook · YouTube</p></address></div>
    </div>
    <div className="border-t border-white/10 py-5 text-center text-xs text-white/55">© {new Date().getFullYear()} JeevaSetu Wellness. All rights reserved.</div>
  </footer>;
}
