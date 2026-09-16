"use client";

import Image from "next/image";
import { useState } from "react";

import type { TherapyOption } from "@/lib/appointments/contracts";
import { getTherapyMedia } from "@/lib/public-site/therapy-media";

const FALLBACK_IMAGE = "/images/ayurveda-essentials.png";

const genericConcerns = [
  "Goals or concerns discussed during your assessment",
  "Support needs identified by a qualified professional",
];

export function TherapySelectionCard({ therapy, selected, onToggle }: {
  therapy: TherapyOption;
  selected: boolean;
  onToggle: () => void;
}) {
  const media = getTherapyMedia(therapy.slug, therapy.name);
  const [imageSrc, setImageSrc] = useState(media.src);
  const [expanded, setExpanded] = useState(false);
  const panelId = `therapy-information-${therapy.id}`;
  const concerns = therapy.benefits?.filter((item) => item.trim()).slice(0, 4) ?? [];
  const commonlyUsedFor = therapy.short_description?.trim()
    || "This service may be considered as part of an individual care or wellbeing plan after discussing your needs.";
  const whatHappens = therapy.detailed_description?.trim()
    || "A qualified professional discusses your needs and explains the session before providing suitable care.";

  return <article className={`min-w-0 overflow-hidden rounded-xl border transition-colors ${selected ? "border-emerald-700 bg-emerald-50 ring-1 ring-emerald-700" : "border-slate-200 bg-white"}`}>
    <button
      type="button"
      aria-pressed={selected}
      aria-label={`Select ${therapy.name}`}
      onClick={onToggle}
      className="flex min-h-16 w-full min-w-0 items-center gap-3 p-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-700 sm:p-4"
    >
      <span className="relative h-11 w-11 shrink-0 overflow-hidden rounded-full bg-[#e9efe8] sm:h-12 sm:w-12">
        <Image
          src={imageSrc}
          alt={media.alt}
          fill
          sizes="48px"
          className="object-cover"
          onError={() => setImageSrc(FALLBACK_IMAGE)}
        />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block break-words font-semibold leading-tight text-[#163c2a]">{therapy.name}</span>
        <span className="mt-1 block text-sm text-slate-600">₹{Number(therapy.base_price ?? 0).toLocaleString("en-IN")}</span>
      </span>
      <span aria-hidden="true" className={`grid h-6 w-6 shrink-0 place-items-center rounded-full border text-sm font-bold ${selected ? "border-emerald-700 bg-emerald-700 text-white" : "border-slate-300 text-transparent"}`}>✓</span>
    </button>

    <button
      type="button"
      aria-expanded={expanded}
      aria-controls={panelId}
      onClick={(event) => { event.stopPropagation(); setExpanded((value) => !value); }}
      className="flex min-h-11 w-full items-center justify-between gap-3 border-t border-slate-200 px-3 py-2 text-left text-sm font-semibold text-emerald-800 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-700 sm:px-4"
    >
      <span>Know about this therapy</span>
      <span aria-hidden="true" className={`shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`}>⌄</span>
    </button>

    {expanded && <div id={panelId} className="grid min-w-0 gap-3 border-t border-slate-200 bg-slate-50 px-3 py-4 text-sm leading-5 text-slate-700 sm:px-4">
      <section>
        <h4 className="font-semibold text-[#163c2a]">Commonly used for</h4>
        <p className="mt-1 break-words">{commonlyUsedFor}</p>
      </section>
      <section>
        <h4 className="font-semibold text-[#163c2a]">Common symptoms or concerns</h4>
        <ul className="mt-1 list-disc space-y-0.5 pl-5">
          {(concerns.length ? concerns : genericConcerns).map((item) => <li key={item} className="break-words">{item}</li>)}
        </ul>
      </section>
      <section>
        <h4 className="font-semibold text-[#163c2a]">What happens during the therapy</h4>
        <p className="mt-1 break-words">{whatHappens}</p>
      </section>
      <aside className="rounded-lg bg-amber-50 p-3 text-xs leading-5 text-amber-950">
        <strong>Important note:</strong> This information is general guidance, not a diagnosis or guarantee of results. Suitability depends on your individual condition and professional assessment.
      </aside>
    </div>}
  </article>;
}
