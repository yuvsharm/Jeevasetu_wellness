import Image from "next/image";
import Link from "next/link";
import { therapies } from "@/lib/public-site/content";

export function TherapyGrid({ limit }: { limit?: number }) {
  return <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">{therapies.slice(0, limit).map((therapy, index) => <article key={therapy.name} id={therapy.name.toLowerCase().replaceAll(" ", "-")} className="card group overflow-hidden">
    <div className="relative aspect-[4/3] overflow-hidden"><Image src={index % 3 === 0 ? "/images/ayurveda-home-service.png" : index % 3 === 1 ? "/images/ayurveda-essentials.png" : "/images/ayurveda-hero.png"} alt={`${therapy.name} Ayurvedic home wellness service`} fill className="object-cover transition duration-700 group-hover:scale-105" sizes="(max-width: 768px) 100vw, 33vw" /></div>
    <div className="p-6"><div className="flex items-start justify-between gap-4"><h3 className="font-serif text-2xl text-[#103c27]">{therapy.name}</h3><strong className="text-[#0b6b3a]">{therapy.price}</strong></div><p className="mt-3 text-sm leading-6 text-[#5b6c63]">{therapy.description}</p>{!limit && <><p className="mt-4 text-xs font-bold tracking-widest text-[#9b7427] uppercase">{therapy.duration} · Home visit available</p><ul className="mt-4 flex flex-wrap gap-2">{therapy.benefits.map(item => <li key={item} className="rounded-full bg-[#edf7ef] px-3 py-1 text-xs text-[#0b6b3a]">{item}</li>)}</ul></>}<Link href={limit ? `/therapies#${therapy.name.toLowerCase().replaceAll(" ", "-")}` : "/contact#booking"} className="mt-5 inline-flex font-semibold text-[#0b6b3a]">{limit ? "View details →" : "Book appointment →"}</Link></div>
  </article>)}</div>;
}
