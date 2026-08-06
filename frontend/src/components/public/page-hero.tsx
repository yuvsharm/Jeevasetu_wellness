export function PageHero({ eyebrow, title, children }: { eyebrow: string; title: string; children: React.ReactNode }) {
  return <section className="overflow-hidden bg-[#f4efe3] py-20 sm:py-28"><div className="site-container"><p className="eyebrow">{eyebrow}</p><h1 className="mt-4 max-w-4xl font-serif text-5xl leading-[1.05] text-[#103c27] sm:text-6xl">{title}</h1><div className="mt-6 max-w-2xl text-lg leading-8 text-[#466254]">{children}</div></div></section>;
}
