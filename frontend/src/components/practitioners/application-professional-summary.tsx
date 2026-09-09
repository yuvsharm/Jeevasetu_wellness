"use client";

import Image from "next/image";
import { formatExperience } from "@/components/staff/staff-creation-wizard";
import type { PractitionerApplication } from "@/lib/practitioners/contracts";

export function ApplicationProfessionalSummary({ application: value }: { application: PractitionerApplication }) {
  const therapies = value.competencies.filter(item => item.verification_status !== "REJECTED");
  return <div className="mt-4 space-y-4">
    {value.has_profile_photo && <a href={`/api/practitioners/applications/${value.id}/profile-photo`} target="_blank" rel="noreferrer" className="font-bold text-emerald-800"><Image src={`/api/practitioners/applications/${value.id}/profile-photo`} alt={`${value.full_legal_name} application photograph`} width={96} height={96} unoptimized className="mb-2 rounded-xl object-cover"/>View private profile photograph</a>}
    <dl className="grid gap-3 text-sm sm:grid-cols-2">{[
      ["Practitioner Type", value.category === "WELLNESS" ? "Naturopathy Practitioner" : "Physiotherapist"],
      ["Qualification", value.qualification_title || value.highest_qualification],
      ["Specialization", value.specialization],
      ["Experience", formatExperience(value.experience_years, value.experience_months)],
      ["Service Areas", value.service_area_names?.join(", ")],
      ["Working Days", value.working_days?.map(day => ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][day]).join(", ")],
      ["Working Hours", value.working_hours_start && value.working_hours_end ? `${value.working_hours_start}–${value.working_hours_end}` : value.availability_notes],
      ["Professional Bio", value.bio],
    ].map(([label, content]) => content ? <div key={label}><dt className="font-bold">{label}</dt><dd>{content}</dd></div> : null)}</dl>
    <h4 className="font-bold">Therapy Competencies</h4>
    <div className="grid gap-2">{therapies.map(item => <div key={item.id}>{item.therapy_name}</div>)}</div>
  </div>;
}
