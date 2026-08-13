import Image from "next/image";
import Link from "next/link";

import { enabledPublicFeatures, type PublicFeature } from "@/lib/public-site/features";

export function FeatureCard({ feature, duplicate = false }: { feature: PublicFeature; duplicate?: boolean }) {
  return <article className="showcase-card group" data-feature-slug={feature.slug}>
    <div className={`showcase-media showcase-media-${feature.category}`}>
      {feature.mediaType === "image" && feature.image && <Image src={feature.image} alt="" fill sizes="(max-width: 640px) 82vw, 25rem" className="object-cover transition-transform duration-700 group-hover:scale-105 group-focus-within:scale-105"/>}
      {feature.mediaType === "video" && feature.video && <video muted loop playsInline preload="none" poster={feature.poster} aria-hidden="true"><source src={feature.video} type="video/mp4"/></video>}
      {feature.mediaType === "graphic" && <span className="showcase-visual" aria-hidden="true">{feature.visual}</span>}
      <div className="showcase-overlay"/>
      <span className="showcase-category">{feature.category === "care" ? "Home care" : feature.category === "journey" ? "Care journey" : "JeevaSetu platform"}</span>
    </div>
    <div className="showcase-copy"><h3 className="font-serif text-3xl leading-tight text-[#103c27]">{feature.title}</h3><p className="mt-3 text-sm leading-6 text-[#5b6c63]">{feature.description}</p><Link href={feature.href} tabIndex={duplicate ? -1 : undefined} aria-hidden={duplicate || undefined} className="showcase-link">{feature.ctaLabel}<span aria-hidden="true">→</span></Link></div>
  </article>;
}

export function FeatureShowcase() {
  const features = enabledPublicFeatures();
  return <section className="showcase-section" aria-labelledby="feature-showcase-title">
    <div className="site-container"><p className="eyebrow">Experience JeevaSetu</p><div className="mt-4 grid gap-5 lg:grid-cols-[1fr_.8fr] lg:items-end"><h2 id="feature-showcase-title" className="font-serif text-4xl leading-tight text-[#103c27] sm:text-5xl">Home wellness meets a structured care journey.</h2><p className="max-w-xl text-base leading-7 text-[#5b6c63]">JeevaSetu connects home-service wellness and physiotherapy with clear booking, reviewed practitioners, visit verification, and thoughtful digital coordination.</p></div></div>
    <div className="showcase-viewport mt-10" aria-label="JeevaSetu features"><div className="showcase-track"><div className="showcase-group">{features.map((feature) => <FeatureCard feature={feature} key={feature.slug}/>)}</div><div className="showcase-group" aria-hidden="true">{features.map((feature) => <FeatureCard feature={feature} duplicate key={`duplicate-${feature.slug}`}/>)}</div></div></div>
  </section>;
}
