import Link from "next/link";

import { Wordmark } from "@/components/brand/wordmark";
import { contact } from "@/lib/public-site/content";

export function PublicFooter() {
  return <footer className="bg-[#073d25] text-white">
    <div className="site-container grid gap-10 py-14 md:grid-cols-3">
      <div><Wordmark inverted publicSite /><p className="mt-5 max-w-sm text-sm leading-7 text-white/70">Professional physiotherapy and wellness services, coordinated for the comfort of home in Meerut.</p><Link href="/book-appointment" className="button-gold mt-6">Book Appointment</Link></div>
      <div><h2 className="footer-heading">Explore JeevaSetu</h2><div className="mt-4 grid grid-cols-2 gap-3 text-sm text-white/75"><Link href="/therapies">Therapies</Link><Link href="/packages">Plans &amp; Offers</Link><Link href="/customer-login">Customer Login</Link><Link href="/work-with-us">Join With Us</Link><Link href="/contact">Contact</Link><Link href="/faq">FAQ</Link><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link></div></div>
      <div><h2 className="footer-heading">Contact</h2><address className="mt-4 space-y-2 text-sm not-italic leading-7 text-white/75"><a href={contact.phoneHref}>{contact.phone}</a><br/><a href={`mailto:${contact.email}`}>{contact.email}</a><p>{contact.address}</p><p>Home-service appointments in and around Meerut.</p></address></div>
    </div>
    <div className="border-t border-white/10 py-5 text-center text-xs text-white/55">© {new Date().getFullYear()} JeevaSetu Wellness. All rights reserved.</div>
  </footer>;
}
