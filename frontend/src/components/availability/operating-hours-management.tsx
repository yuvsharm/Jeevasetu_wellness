"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useSession } from "@/components/auth/session-provider";
import { requestJson } from "@/lib/api/client";

type Day = { weekday: number; is_open: boolean; opens_at: string | null; closes_at: string | null };
type Hours = { clinic: string; clinic_name: string; timezone: string; configured: boolean; minimum_advance_notice_hours: number; days: Day[] };

const names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const blankDays = (): Day[] => names.map((_, weekday) => ({ weekday, is_open: false, opens_at: null, closes_at: null }));

export function OperatingHoursManagement() {
  const session = useSession();
  const client = useQueryClient();
  const clinics = session.data?.access.permitted_clinics ?? [];
  const [clinic, setClinic] = useState("");
  const [drafts, setDrafts] = useState<Record<string, Day[]>>({});
  const [noticeDrafts, setNoticeDrafts] = useState<Record<string, number>>({});
  const selectedClinic = clinic || clinics[0]?.id || "";
  const hours = useQuery({ queryKey: ["operating-hours", selectedClinic], queryFn: () => requestJson<Hours>(`/api/availability/operating-hours/${selectedClinic}`), enabled: Boolean(selectedClinic) });
  const days = drafts[selectedClinic] ?? hours.data?.days ?? blankDays();
  const minimumNotice = noticeDrafts[selectedClinic] ?? hours.data?.minimum_advance_notice_hours ?? 24;
  const save = useMutation({
    mutationFn: () => requestJson<Hours>(`/api/availability/operating-hours/${selectedClinic}`, { method: "PUT", body: JSON.stringify({ days, minimum_advance_notice_hours: minimumNotice }) }),
    onSuccess: async (value) => {
      setDrafts((current) => ({ ...current, [selectedClinic]: value.days }));
      setNoticeDrafts((current) => ({ ...current, [selectedClinic]: value.minimum_advance_notice_hours }));
      await client.invalidateQueries({ queryKey: ["operating-hours", selectedClinic] });
    },
  });
  const update = (weekday: number, patch: Partial<Day>) => setDrafts((current) => ({
    ...current,
    [selectedClinic]: days.map((day) => day.weekday === weekday ? { ...day, ...patch } : day),
  }));

  return <section id="operating-hours" className="mt-8 rounded-2xl border bg-white p-5">
    <h2 className="text-2xl font-bold">Clinic service hours</h2>
    <p className="mt-1 text-slate-600">Configure the customer booking window for each clinic. Closed days produce no online slots.</p>
    <label className="mt-5 grid max-w-md gap-1 font-semibold">Clinic<select value={selectedClinic} onChange={(event) => setClinic(event.target.value)} className="min-h-11 rounded-xl border px-3">{clinics.map((value) => <option key={value.id} value={value.id}>{value.slug}</option>)}</select></label>
    {!selectedClinic && <p className="mt-4 text-amber-800">No permitted clinic is available for this account.</p>}
    {hours.isPending && selectedClinic && <p className="mt-4">Loading service hours…</p>}
    {selectedClinic && !hours.isPending && <div className="mt-5 space-y-3">
      {days.map((day) => <div key={day.weekday} className="grid items-center gap-3 rounded-xl border p-3 sm:grid-cols-[9rem_7rem_1fr_1fr]">
        <strong>{names[day.weekday]}</strong>
        <label className="flex items-center gap-2"><input type="checkbox" checked={day.is_open} onChange={(event) => update(day.weekday, { is_open: event.target.checked, opens_at: event.target.checked ? day.opens_at ?? "09:00" : null, closes_at: event.target.checked ? day.closes_at ?? "18:00" : null })} /> Open</label>
        <label className="grid gap-1 text-sm">Opening time<input aria-label={`${names[day.weekday]} opening time`} type="time" disabled={!day.is_open} value={day.opens_at ?? ""} onChange={(event) => update(day.weekday, { opens_at: event.target.value })} className="min-h-10 rounded-lg border px-3" /></label>
        <label className="grid gap-1 text-sm">Closing time<input aria-label={`${names[day.weekday]} closing time`} type="time" disabled={!day.is_open} value={day.closes_at ?? ""} onChange={(event) => update(day.weekday, { closes_at: event.target.value })} className="min-h-10 rounded-lg border px-3" /></label>
      </div>)}
      <label className="grid max-w-md gap-1 font-semibold">Minimum advance booking notice
        <span className="text-sm font-normal text-slate-600">Hours before the appointment starts (1–168)</span>
        <input type="number" min="1" max="168" value={minimumNotice} onChange={(event) => setNoticeDrafts((current) => ({ ...current, [selectedClinic]: Number(event.target.value) }))} className="min-h-11 rounded-xl border px-3" />
      </label>
      <p className="text-sm text-slate-600">Timezone: {hours.data?.timezone || "Clinic timezone"}</p>
      <button type="button" disabled={save.isPending || !days.some((day) => day.is_open)} onClick={() => save.mutate()} className="min-h-11 rounded-xl bg-emerald-700 px-5 font-bold text-white disabled:opacity-50">{save.isPending ? "Saving…" : "Save service hours"}</button>
      {save.isSuccess && <p role="status" className="text-emerald-800">Service hours saved.</p>}
      {(save.isError || hours.isError) && <p role="alert" className="text-red-700">{(save.error || hours.error)?.message}</p>}
    </div>}
  </section>;
}
