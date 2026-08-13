import Image from "next/image";
import Link from "next/link";
import { BookingEntry } from "@/components/public/booking-entry";
import { FaqList } from "@/components/public/faq-list";
import { PublicShell } from "@/components/public/public-shell";
import { SectionHeading } from "@/components/public/section-heading";
import { TherapyGrid } from "@/components/public/therapy-grid";
import { contact, strengths } from "@/lib/public-site/content";

export default function Home() { return <PublicShell><main>
  <section className="hero-section relative isolate overflow-hidden">
    <Image src="/images/ayurveda-hero.png" alt="JeevaSetu professional preparing a home wellness service" fill priority className="hero-media object-cover" sizes="100vw"/>
    <div className="hero-scrim absolute inset-0"/>
    <div className="site-container relative grid min-h-[690px] items-center gap-12 py-20 lg:grid-cols-[minmax(0,1fr)_22rem] lg:py-28">
      <div className="max-w-3xl">
        <p className="eyebrow hero-reveal">Professional home wellness · Meerut</p>
        <h1 className="hero-title hero-reveal mt-6 font-serif font-normal tracking-[-.045em] text-[#103c27]">Expert wellness &amp; physiotherapy <em>at your doorstep.</em></h1>
        <p className="hero-reveal mt-7 max-w-2xl text-lg leading-8 text-[#405f4f]">Request personalized home-service care, explore JeevaSetu therapies, and move from booking to a professionally coordinated visit with clarity at every step.</p>
        <div className="hero-reveal mt-9 flex flex-wrap gap-3"><Link href="/book-appointment" className="button-primary">Book appointment <span aria-hidden="true">→</span></Link><Link href="/therapies" className="button-secondary">Explore therapies</Link></div>
        <ul className="hero-reveal mt-9 flex flex-wrap gap-x-6 gap-y-3 text-sm font-semibold text-[#345444]" aria-label="JeevaSetu service highlights"><li>Home-service focused</li><li>Structured appointment journey</li><li>OTP-verified visits</li></ul>
        <p className="hero-reveal mt-6 text-xs leading-5 text-[#68786f]">Wellness services are not a substitute for medical diagnosis or emergency care.</p>
      </div>
      <div className="hero-note hidden rounded-[2rem] border border-white/60 bg-white/70 p-6 shadow-2xl shadow-emerald-950/10 backdrop-blur-xl lg:block"><span className="grid size-12 place-items-center rounded-full bg-[#0b6b3a] text-xl text-white" aria-hidden="true">⌂</span><p className="mt-6 text-xs font-bold uppercase tracking-[.18em] text-[#9b7427]">Care that comes to you</p><p className="mt-3 font-serif text-3xl leading-tight text-[#103c27]">Thoughtful support, coordinated for the comfort of home.</p><Link href="/why-choose-us" className="mt-6 inline-flex items-center gap-2 font-bold text-[#0b6b3a]">Why JeevaSetu <span aria-hidden="true">↗</span></Link></div>
    </div>
    <div className="site-container relative -mb-20 translate-y-0 pb-4"><BookingEntry/></div>
  </section>
  <section className="section pt-32"><div className="site-container"><SectionHeading eyebrow="Why JeevaSetu" title="Ayurveda, thoughtfully brought home" copy="A calm, considered experience built around trust, traditional care, and the realities of modern life."/><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{strengths.map(([title, copy], i) => <article key={title} className="feature-card"><span className="feature-number">0{i + 1}</span><h3 className="mt-6 font-serif text-2xl text-[#103c27]">{title}</h3><p className="mt-3 text-sm leading-6 text-[#5b6c63]">{copy}</p></article>)}</div></div></section>
  <section className="section bg-[#f7f3e9]"><div className="site-container"><SectionHeading eyebrow="Our therapies" title="Traditional care, tailored to you" copy="Explore the ten therapies currently offered by JeevaSetu Wellness."/><TherapyGrid limit={6}/><div className="mt-10 text-center"><Link href="/therapies" className="button-secondary">Explore all therapies</Link></div></div></section>
  <section className="section"><div className="site-container grid items-center gap-12 lg:grid-cols-2"><div className="relative aspect-[4/3] overflow-hidden rounded-[2.5rem]"><Image src="/images/ayurveda-home-service.png" alt="Prepared JeevaSetu home therapy room" fill className="object-cover" sizes="50vw"/></div><div><SectionHeading eyebrow="Wellness packages" title="A consistent rhythm for your wellbeing" copy="Choose a 5, 7, or 10-session plan, explore a combo, or speak with us about a customized package."/><div className="grid grid-cols-2 gap-3">{["5 Sessions", "7 Sessions", "10 Sessions", "Combo Packages"].map(item => <div className="rounded-2xl border border-[#0b6b3a]/15 p-5 font-semibold text-[#0b6b3a]" key={item}>{item}<span className="mt-1 block text-xs font-normal text-[#68786f]">Validity confirmed at booking</span></div>)}</div><Link href="/packages" className="button-primary mt-7">View packages</Link></div></div></section>
  <section className="section bg-[#0b6b3a] text-white"><div className="site-container"><SectionHeading eyebrow="Why choose us" title="Quiet confidence in every visit" copy="Professional conduct, careful preparation, and care that respects your home."/><div className="grid gap-6 md:grid-cols-3">{strengths.slice(0,3).map(([title, copy]) => <div key={title} className="rounded-3xl border border-white/15 p-7"><h3 className="font-serif text-2xl">{title}</h3><p className="mt-3 text-sm leading-7 text-white/70">{copy}</p></div>)}</div></div></section>
  <section className="section bg-[#f7f3e9]"><div className="site-container"><SectionHeading eyebrow="Questions, answered" title="Know what to expect" center/><FaqList limit={4}/><div className="mt-8 text-center"><Link href="/faq" className="button-quiet">Read all FAQs</Link></div></div></section>
  <section className="section"><div className="site-container rounded-[2.5rem] bg-[#173d2a] px-7 py-14 text-center text-white sm:px-14"><p className="eyebrow text-[#e2c679]">Your wellness, closer to home</p><h2 className="mx-auto mt-4 max-w-3xl font-serif text-4xl sm:text-5xl">Ready to begin a more thoughtful care routine?</h2><div className="mt-8 flex flex-wrap justify-center gap-3"><Link href="/book-appointment" className="button-gold">Book appointment</Link><a href={contact.whatsapp} className="button-light" target="_blank" rel="noreferrer">WhatsApp</a><a href={contact.phoneHref} className="button-light">Call now</a></div></div></section>
</main></PublicShell>; }
