"use client";

import Image from "next/image";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { requestJson } from "@/lib/api/client";
import type { PublicPractitioner } from "@/lib/practitioners/contracts";

const loadPractitioners = () => requestJson<PublicPractitioner[]>("/api/practitioners/public");

function PractitionerCard({ item, compact = false }: { item: PublicPractitioner; compact?: boolean }) {
  const expertise = item.verified_services.length ? item.verified_services : item.qualification_specialization ? [item.qualification_specialization] : [];
  return <article className={`card overflow-hidden ${compact ? "w-[18rem] shrink-0 snap-start sm:w-[20rem]" : ""}`}>
    <div className="relative aspect-[4/3] bg-[#edf7ef]">{item.photo_url ? <Image src={item.photo_url} alt={`${item.display_name} professional profile`} fill className="object-cover" unoptimized /> : <div className="grid h-full place-items-center text-5xl font-bold text-[#0b6b3a]">{item.display_name.charAt(0)}</div>}</div>
    <div className="p-5"><span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-bold text-emerald-900">✓ JeevaSetu Verified</span><h3 className="mt-4 font-serif text-2xl text-[#103c27]">{item.display_name}</h3><p className="mt-2 font-semibold text-[#0b6b3a]">{item.highest_qualification}{item.qualification_specialization ? ` · ${item.qualification_specialization}` : ""}</p><p className="mt-2 text-sm text-[#5b6c63]">{item.experience_years} years experience · {item.gender}</p><p className="mt-1 text-sm text-[#5b6c63]">{item.average_rating ? `${item.average_rating.toFixed(1)} ★` : "New practitioner"} · {item.review_count} approved review{item.review_count === 1 ? "" : "s"}</p>{item.languages.length > 0 && <p className="mt-1 text-sm text-[#5b6c63]">Languages: {item.languages.join(", ")}</p>}{item.service_area && <p className="mt-1 text-sm text-[#5b6c63]">Service area: {item.service_area}</p>}{expertise.length > 0 && <div className="mt-4 flex flex-wrap gap-2">{expertise.map((service) => <span key={service} className="rounded-full border border-[#0b6b3a]/20 px-3 py-1 text-xs">{service}</span>)}</div>}{item.bio && <p className="mt-4 line-clamp-3 text-sm leading-6 text-[#5b6c63]">{item.bio}</p>}</div>
  </article>;
}

export function PublicPractitionerDirectory() {
  const query = useQuery({ queryKey: ["public-practitioners"], queryFn: loadPractitioners });
  return <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">{query.data?.map((item) => <PractitionerCard key={item.id} item={item} />)}{query.isPending && <p>Loading verified practitioners…</p>}{query.data?.length === 0 && <p className="text-[#5b6c63]">Verified practitioner profiles will appear here as they become available.</p>}</div>;
}

export function PractitionerCarousel() {
  const query = useQuery({ queryKey: ["public-practitioners"], queryFn: loadPractitioners });
  const track = useRef<HTMLDivElement>(null);
  const [paused, setPaused] = useState(false);
  const move = (direction: 1 | -1) => { const element = track.current; if (!element) return; const distance = Math.min(336, element.clientWidth * 0.9) * direction; const atEnd = element.scrollLeft + element.clientWidth >= element.scrollWidth - 8; const atStart = element.scrollLeft <= 8; element.scrollTo({ left: direction > 0 && atEnd ? 0 : direction < 0 && atStart ? element.scrollWidth : element.scrollLeft + distance, behavior: "smooth" }); };
  useEffect(() => { if (paused || (query.data?.length ?? 0) < 2) return; const timer = window.setInterval(() => move(1), 5000); return () => window.clearInterval(timer); }, [paused, query.data?.length]);
  return <section aria-labelledby="experienced-practitioners-heading" className="rounded-3xl border border-emerald-100 bg-white p-5 sm:p-7"><div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-bold uppercase tracking-[.15em] text-[#9b7427]">JeevaSetu verified</p><h2 id="experienced-practitioners-heading" className="mt-2 text-3xl font-bold text-slate-950">Our Experienced Practitioners</h2><p className="mt-2 text-slate-600">Meet approved professionals available through JeevaSetu.</p></div>{(query.data?.length ?? 0) > 1 && <div className="flex gap-2"><button type="button" aria-label="Previous practitioners" onClick={() => move(-1)} className="min-h-11 rounded-xl border border-emerald-700 px-4 font-bold text-emerald-800">←</button><button type="button" aria-label="Next practitioners" onClick={() => move(1)} className="min-h-11 rounded-xl border border-emerald-700 px-4 font-bold text-emerald-800">→</button></div>}</div>{query.isPending && <p className="mt-6 text-slate-600">Loading verified practitioners…</p>}{query.isError && <p className="mt-6 text-red-700">Practitioner profiles could not be loaded.</p>}{query.data?.length === 0 && <p className="mt-6 rounded-2xl border border-dashed p-6 text-center text-slate-600">Verified practitioner profiles will appear here as they become available.</p>}{(query.data?.length ?? 0) > 0 && <div ref={track} tabIndex={0} aria-label="Verified practitioner carousel" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)} onFocus={() => setPaused(true)} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setPaused(false); }} className="mt-6 flex snap-x snap-mandatory gap-5 overflow-x-auto scroll-smooth pb-3 focus-visible:outline-2 focus-visible:outline-emerald-700">{query.data?.map((item) => <PractitionerCard key={item.id} item={item} compact />)}</div>}</section>;
}
