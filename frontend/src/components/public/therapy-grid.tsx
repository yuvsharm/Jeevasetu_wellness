"use client";

import Image from "next/image";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { requestJson } from "@/lib/api/client";
import type { CommercialCatalog } from "@/lib/appointments/contracts";
import { getTherapyMedia } from "@/lib/public-site/therapy-media";

const money=(value:string|undefined)=>`₹${Number(value??0).toLocaleString("en-IN")}`;
const validity=(from:string|null,until:string|null)=>{
  if(!from&&!until)return "Available while active";
  const format=(value:string)=>new Intl.DateTimeFormat("en-IN",{dateStyle:"medium"}).format(new Date(value));
  const inclusiveEnd=until?new Date(new Date(until).getTime()-1).toISOString():null;
  if(from&&inclusiveEnd)return `Valid ${format(from)} – ${format(inclusiveEnd)}`;
  return from?`Valid from ${format(from)}`:`Valid until ${format(until!)}`;
};
const catalogQuery=()=>requestJson<CommercialCatalog>("/api/commercial/public");
export function TherapyGrid({limit,compact=false}:{limit?:number;compact?:boolean}){
  const query=useQuery({queryKey:["commercial-public"],queryFn:catalogQuery});
  const therapies=(query.data?.therapies??[]).slice(0,limit);
  if(query.isPending)return <p className="py-8 text-center text-[#5b6c63]">Loading current therapies…</p>;
  if(query.isError)return <p className="py-8 text-center text-red-700">Current therapies could not be loaded.</p>;
  if(!therapies.length)return <p className="rounded-3xl border border-dashed border-[#0b6b3a]/25 p-8 text-center text-[#5b6c63]">No therapies are publicly available right now. Please contact NuriPain Ease for availability.</p>;
  return <div className={`grid gap-4 ${compact?"sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5":"sm:grid-cols-2 lg:grid-cols-3"}`}>{therapies.map(therapy=>{const media=getTherapyMedia(therapy.slug,therapy.name);return <article key={therapy.id} id={therapy.slug} className="card group min-w-0 overflow-hidden"><div className="relative aspect-[5/2] overflow-hidden bg-[#e9efe8]"><Image src={media.src} alt={media.alt} fill className="object-cover transition duration-500 group-hover:scale-105" sizes={compact?"(max-width: 639px) 100vw, (max-width: 1023px) 33vw, 20vw":"(max-width: 639px) 100vw, 33vw"}/></div><div className="flex h-[calc(100%-var(--therapy-media-height,0px))] flex-col p-4"><p className="text-[.68rem] font-bold uppercase tracking-[.12em] text-[#9b7427]">Home service · {therapy.default_duration_minutes??45} min</p><h3 className="mt-1.5 break-words font-serif text-xl leading-tight text-[#103c27]">{therapy.name}</h3><strong className="mt-2 block text-lg text-[#0b6b3a]">{money(therapy.base_price)}<span className="text-xs font-medium text-[#5b6c63]"> / session</span></strong><p className="mt-2 line-clamp-3 break-words text-sm leading-5 text-[#5b6c63]">{therapy.short_description||therapy.detailed_description||"Professional home-service care coordinated by NuriPain Ease."}</p><div className="mt-auto flex flex-wrap items-center gap-1.5 pt-4"><Link href={`/book-appointment?therapy=${therapy.id}`} aria-label={`Book ${therapy.name}`} className="button-primary !min-h-11 !px-3">Book</Link><Link href={`/therapies#${therapy.slug}`} aria-label={`View details for ${therapy.name}`} className="button-quiet !min-h-11 !px-2">View details</Link></div></div></article>})}</div>;
}

const isCurrentPublicItem=(item:{is_active?:boolean;is_publicly_visible?:boolean;valid_from:string|null;valid_until:string|null})=>{
  const now=Date.now();
  return item.is_active!==false&&item.is_publicly_visible!==false&&(!item.valid_from||new Date(item.valid_from).getTime()<=now)&&(!item.valid_until||new Date(item.valid_until).getTime()>now);
};

export function CommercialOffers({limit,dashboard=false}:{limit?:number;dashboard?:boolean}){
  const query=useQuery({queryKey:["commercial-public"],queryFn:catalogQuery});
  const catalog=query.data;
  const packages=(catalog?.packages??[]).filter(isCurrentPublicItem).slice(0,limit);
  const offers=(catalog?.offers??[]).filter(isCurrentPublicItem).slice(0,limit);
  if(dashboard&&(query.isPending||query.isError||!offers.length))return null;
  if(query.isPending)return <p className="py-8 text-center text-[#5b6c63]">Loading current plans and offers…</p>;
  if(query.isError)return <p className="py-8 text-center text-red-700">Plans and offers could not be loaded.</p>;
  if(!catalog||(!packages.length&&!offers.length))return <div className="rounded-3xl border border-dashed border-[#0b6b3a]/25 bg-white/60 p-8 text-center"><h3 className="font-serif text-2xl text-[#103c27]">Simple, transparent session pricing</h3><p className="mt-2 text-sm text-[#5b6c63]">There are no active public promotions right now. You can still book any available therapy at its current session price.</p><Link href="/therapies" className="button-secondary mt-5">View therapies</Link></div>;
  const cardClass=dashboard?"offer-card w-[min(85vw,24rem)] shrink-0 snap-start":"offer-card min-w-0";
  const cards=<>
    {packages.map(item=><article key={item.id} className={cardClass}><p className="text-xs font-bold uppercase tracking-[.15em] text-[#9b7427]">Session plan</p><h3 className="mt-2 break-words font-serif text-3xl text-[#103c27]">{item.name}</h3><p className="mt-2 text-sm text-[#5b6c63]">{item.therapy_name} · {item.session_count} sessions</p><p className="mt-2 text-xs font-semibold text-[#5b6c63]">{validity(item.valid_from,item.valid_until)}</p><div className="mt-5 rounded-2xl bg-[#f7f3e9] p-4"><p><s className="text-slate-500">Regular {money(item.regular_total)}</s></p><p className="mt-1 text-2xl font-bold text-[#0b6b3a]">Offer {money(item.selling_price)}</p><p className="mt-1 text-sm font-semibold">Save {money(item.saving)} · {item.discount_percentage}%</p></div>{item.description&&<p className="mt-4 line-clamp-2 text-sm text-[#5b6c63]">{item.description}</p>}<Link href={`/book-appointment?package=${item.id}`} className="button-primary mt-5">Choose plan</Link></article>)}
    {offers.map(item=><article key={item.id} className={cardClass}><p className="text-xs font-bold uppercase tracking-[.15em] text-[#9b7427]">{item.offer_type==="FIXED_BUNDLE"?"Therapy combo":item.offer_type==="FAMILY"||item.offer_type==="FAMILY_FREE"?"Family offer":item.offer_type==="FREE_THERAPY"?"Free add-on offer":"Current offer"}</p><h3 className="mt-2 break-words font-serif text-3xl text-[#103c27]">{item.title}</h3><p className="mt-2 break-words text-sm text-[#5b6c63]">{item.promotional_text}</p>{item.offer_type==="PERCENTAGE"&&<p className="mt-3 text-xl font-bold text-[#0b6b3a]">{item.discount_value}% OFF</p>}{item.offer_type==="FAMILY"&&<p className="mt-3 text-xl font-bold text-[#0b6b3a]">Family booking saves {item.discount_value}%</p>}{item.offer_type==="FIXED_DISCOUNT"&&<p className="mt-3 text-xl font-bold text-[#0b6b3a]">{money(item.discount_value)} OFF</p>}{item.offer_type==="FIXED_BUNDLE"&&<p className="mt-3 text-xl font-bold text-[#0b6b3a]">Bundle price {money(item.fixed_price??undefined)}</p>}{(item.offer_type==="FREE_THERAPY"||item.offer_type==="FAMILY_FREE")&&<p className="mt-3 text-xl font-bold text-[#0b6b3a]">Free {item.free_therapy_name}</p>}<p className="mt-3 font-semibold text-[#294d3a]">Choose any {item.minimum_therapy_count} eligible {item.minimum_therapy_count===1?"therapy":"therapies"}</p><p className="mt-2 break-words text-sm text-[#5b6c63]">Eligible: {item.eligible_therapy_names.join(", ")}</p><p className="mt-2 text-xs font-semibold text-[#5b6c63]">{validity(item.valid_from,item.valid_until)}</p><Link href={`/book-appointment?offer=${item.id}`} className="button-primary mt-5">Choose offer</Link></article>)}
  </>;
  if(dashboard)return <section aria-labelledby="customer-current-offers" className="rounded-3xl bg-[#f7f3e9] p-5 sm:p-7"><div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-bold uppercase tracking-[.15em] text-[#9b7427]">Care savings</p><h2 id="customer-current-offers" className="font-serif text-3xl text-[#103c27]">Current Offers &amp; Packages</h2></div><Link href="/customer/offers" className="font-bold text-emerald-800 underline">View all offers &amp; packages</Link></div><div className="mt-5 flex snap-x gap-5 overflow-x-auto pb-3">{cards}</div></section>;
  return <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">{cards}</div>;
}
