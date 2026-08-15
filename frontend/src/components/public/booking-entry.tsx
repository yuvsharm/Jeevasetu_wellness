"use client";

import { useRouter } from "next/navigation";

export function BookingEntry() {
  const router = useRouter();

  return (
    <button
      type="button"
      onClick={() => router.push("/book-appointment")}
      className="booking-entry w-full cursor-pointer text-left transition-transform hover:-translate-y-1"
      aria-label="Quick Appointment"
    >
      <div>
        <p className="eyebrow">Quick Appointment</p>
        <h2 id="booking-entry-title" className="mt-3 font-serif text-3xl leading-tight text-[#103c27] sm:text-4xl">
          Fast, verified booking for your home wellness visit.
        </h2>
      </div>
      <div className="mt-4 flex items-center justify-between gap-4 rounded-2xl border border-[#0b6b3a]/10 bg-[#edf7ef] p-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#0b6b3a]">Start in under a minute</p>
          <p className="mt-2 text-sm text-[#405f4f]">OTP verified mobile, preferred slot, and multiple therapy preferences.</p>
        </div>
        <span className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-[#0b6b3a] text-2xl text-white" aria-hidden="true">→</span>
      </div>
    </button>
  );
}
