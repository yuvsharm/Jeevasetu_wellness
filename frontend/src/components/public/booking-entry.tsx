"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { requestJson } from "@/lib/api/client";
import type { TherapyOption } from "@/lib/appointments/contracts";

export function BookingEntry() {
  const router = useRouter();
  const [therapy, setTherapy] = useState("");
  const therapies = useQuery({ queryKey: ["appointment-therapies"], queryFn: () => requestJson<TherapyOption[]>("/api/appointment-therapies") });
  function continueBooking(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    router.push(`/book-appointment${therapy ? `?therapy=${encodeURIComponent(therapy)}` : ""}`);
  }
  return <aside className="booking-entry" aria-labelledby="booking-entry-title">
    <div><p className="eyebrow">Start your request</p><h2 id="booking-entry-title" className="mt-3 font-serif text-3xl leading-tight text-[#103c27] sm:text-4xl">Care begins with one simple choice.</h2><p className="mt-3 max-w-xl text-sm leading-6 text-[#5b6c63]">Choose a live JeevaSetu therapy, then continue to the existing secure appointment request.</p></div>
    <form onSubmit={continueBooking} className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]" aria-label="Start appointment request"><label className="form-label">Service or therapy<select className="public-input" value={therapy} onChange={(event) => setTherapy(event.target.value)} disabled={therapies.isPending}><option value="">{therapies.isPending ? "Loading current therapies…" : "Help me choose"}</option>{therapies.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><button className="button-primary self-end" type="submit">Continue booking <span aria-hidden="true">→</span></button>{therapies.isError && <p className="text-sm text-red-700 sm:col-span-2" role="alert">The live therapy list is unavailable. You can still continue and choose on the next page.</p>}</form>
  </aside>;
}
