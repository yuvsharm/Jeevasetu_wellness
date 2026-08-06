"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { requestJson } from "@/lib/api/client";
import type { PatientPage, PatientProfile } from "@/lib/patients/contracts";

type Session = { access: { permitted_clinics: Array<{ id: string; slug: string }> } };

export function PatientDirectory() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [photo, setPhoto] = useState<File | null>(null);
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["patients", search, status],
    queryFn: () => requestJson<PatientPage>(`/api/patients?search=${encodeURIComponent(search)}&status=${status}`),
  });
  const session = useQuery({ queryKey: ["session-patients"], queryFn: () => requestJson<Session>("/api/session/me") });
  const detail = useQuery({
    queryKey: ["patient", selectedId],
    queryFn: () => requestJson<PatientProfile>(`/api/patients/${selectedId}`),
    enabled: Boolean(selectedId),
  });
  const create = useMutation({
    mutationFn: async (value: Record<string, unknown>) => {
      const patient = await requestJson<PatientProfile>("/api/patients", { method: "POST", body: JSON.stringify(value) });
      if (photo) {
        const upload = new FormData();
        upload.set("profile_photo", photo);
        const response = await fetch(`/api/patients/${patient.id}`, { method: "PATCH", body: upload });
        if (!response.ok) throw new Error("The profile was created, but the photograph could not be uploaded.");
      }
      return patient;
    },
    onSuccess: () => { setShowForm(false); setPhoto(null); client.invalidateQueries({ queryKey: ["patients"] }); },
  });
  const toggle = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) => requestJson(`/api/patients/${id}/status`, { method: "POST", body: JSON.stringify({ is_active, reason: "Patient status updated by authorized staff." }) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["patients"] }),
  });

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    create.mutate({
      full_name: data.get("full_name"), mobile_number: data.get("mobile_number"), email: data.get("email"),
      gender: data.get("gender"), age: Number(data.get("age")), clinic: data.get("clinic"),
      emergency_contact_name: data.get("emergency_contact_name"), emergency_contact_relationship: data.get("emergency_contact_relationship"), emergency_contact_mobile: data.get("emergency_contact_mobile"),
      guardian_name: data.get("guardian_name"), guardian_relationship: data.get("guardian_relationship"), guardian_mobile: data.get("guardian_mobile"),
      addresses: [{ label: "Primary", address_line_1: data.get("address_line_1"), address_line_2: "", landmark: data.get("landmark"), city: data.get("city"), region: data.get("region"), pin_code: data.get("pin_code"), is_primary: true, is_active: true }], caregivers: [],
    });
  }

  return <section className="mt-8" aria-labelledby="patients-heading">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><h2 id="patients-heading" className="text-2xl font-bold">Patients</h2><p className="text-slate-600">Clinic-scoped patient profiles with retained audit history.</p></div><button onClick={() => setShowForm(v => !v)} className="min-h-11 rounded-xl bg-emerald-700 px-4 font-bold text-white">{showForm ? "Close form" : "Add patient"}</button></div>
    {showForm && <form onSubmit={submit} aria-label="Create patient" className="mt-5 grid gap-4 rounded-2xl border bg-white p-5 sm:grid-cols-2"><h3 className="text-xl font-bold sm:col-span-2">New patient</h3>
      <Field name="full_name" label="Full name"/><Field name="mobile_number" label="Mobile number"/><Field name="email" label="Email (optional)" required={false} type="email"/>
      <label className="grid gap-1 font-semibold">Gender<select name="gender" className="min-h-11 rounded-xl border px-3"><option value="FEMALE">Female</option><option value="MALE">Male</option><option value="OTHER">Other</option><option value="PREFER_NOT_TO_SAY">Prefer not to say</option></select></label>
      <Field name="age" label="Age" type="number"/><label className="grid gap-1 font-semibold">Assigned clinic<select required name="clinic" className="min-h-11 rounded-xl border px-3"><option value="">Select clinic</option>{session.data?.access?.permitted_clinics.map(c => <option key={c.id} value={c.id}>{c.slug}</option>)}</select></label>
      <h4 className="font-bold sm:col-span-2">Primary address</h4><Field name="address_line_1" label="Address"/><Field name="landmark" label="Landmark" required={false}/><Field name="city" label="City"/><Field name="region" label="State"/><Field name="pin_code" label="PIN code"/>
      <h4 className="font-bold sm:col-span-2">Emergency contact</h4><Field name="emergency_contact_name" label="Name"/><Field name="emergency_contact_relationship" label="Relationship"/><Field name="emergency_contact_mobile" label="Mobile number"/>
      <h4 className="font-bold sm:col-span-2">Guardian details (mandatory below age 18)</h4><Field name="guardian_name" label="Guardian name" required={false}/><Field name="guardian_relationship" label="Relationship" required={false}/><Field name="guardian_mobile" label="Mobile number" required={false}/>
      <label className="grid gap-1 font-semibold sm:col-span-2">Profile photograph (optional, JPG/PNG/WebP, maximum 2 MB)<input type="file" accept="image/jpeg,image/png,image/webp" onChange={event => setPhoto(event.target.files?.[0] ?? null)} className="min-h-11 rounded-xl border p-2"/></label>
      <button disabled={create.isPending} className="min-h-11 rounded-xl bg-emerald-700 px-4 font-bold text-white sm:col-span-2">{create.isPending ? "Creating…" : "Create patient"}</button>{create.isError && <p role="alert" className="text-red-700 sm:col-span-2">{create.error.message}</p>}
    </form>}
    <div className="mt-5 grid gap-3 sm:grid-cols-2"><input aria-label="Search patients" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search name or patient ID" className="min-h-11 rounded-xl border px-3"/><select aria-label="Filter patient status" value={status} onChange={e => setStatus(e.target.value)} className="min-h-11 rounded-xl border px-3"><option value="">All statuses</option><option value="active">Active</option><option value="inactive">Inactive</option></select></div>
    <div className="mt-5 overflow-x-auto rounded-2xl border bg-white"><table className="min-w-full text-left text-sm"><thead className="bg-slate-50"><tr>{["Patient", "Clinic", "Gender / age", "Status", "Actions"].map(h => <th className="p-4" key={h}>{h}</th>)}</tr></thead><tbody>{query.data?.results.map(p => <tr className="border-t" key={p.id}><td className="p-4"><strong>{p.full_name}</strong><span className="block text-slate-500">{p.patient_identifier} · {p.mobile_hint}</span></td><td className="p-4">{p.clinic_name}</td><td className="p-4">{p.gender} · {p.age ?? p.date_of_birth}</td><td className="p-4">{p.is_active ? "Active" : "Inactive"}</td><td className="p-4"><div className="flex gap-3"><button className="font-bold text-emerald-800 underline" onClick={() => setSelectedId(p.id)}>View</button><button className="font-bold text-emerald-800 underline" onClick={() => toggle.mutate({ id:p.id, is_active:!p.is_active })}>{p.is_active ? "Deactivate" : "Activate"}</button></div></td></tr>)}</tbody></table>{query.isPending && <p className="p-5">Loading patients…</p>}{query.data?.results.length === 0 && <p className="p-5">No patients match these filters.</p>}</div>
    {selectedId && <div role="dialog" aria-modal="true" aria-label="Patient details" className="mt-5 rounded-2xl border bg-white p-5"><button onClick={() => setSelectedId(null)} className="float-right font-bold underline">Close</button>{detail.data ? <>{detail.data.profile_photo_url && <img src={`/api/patients/${detail.data.id}/photo`} alt={`${detail.data.full_name} profile`} className="mb-4 size-24 rounded-full object-cover"/>}<h3 className="text-xl font-bold">{detail.data.full_name}</h3><p>{detail.data.patient_identifier}</p><dl className="mt-4 grid gap-3 sm:grid-cols-2"><div><dt className="font-semibold">Mobile</dt><dd>{detail.data.mobile_number}</dd></div><div><dt className="font-semibold">Emergency contact</dt><dd>{detail.data.emergency_contact_name} · {detail.data.emergency_contact_relationship}</dd></div><div><dt className="font-semibold">Primary address</dt><dd>{detail.data.addresses.find(a => a.is_primary)?.address_line_1}</dd></div><div><dt className="font-semibold">Clinic</dt><dd>{detail.data.clinic_name}</dd></div></dl></> : <p>Loading patient details…</p>}</div>}
  </section>;
}

function Field({ name, label, type="text", required=true }: { name:string; label:string; type?:string; required?:boolean }) { return <label className="grid gap-1 font-semibold">{label}<input name={name} type={type} required={required} className="min-h-11 rounded-xl border px-3"/></label>; }
