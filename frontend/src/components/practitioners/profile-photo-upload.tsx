"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { requestJson } from "@/lib/api/client";
import type { PractitionerApplication } from "@/lib/practitioners/contracts";

export function PractitionerProfilePhotoUpload() {
  const [message, setMessage] = useState("");
  const query = useQuery({
    queryKey: ["my-practitioner-applications"],
    queryFn: () => requestJson<PractitionerApplication[]>("/api/practitioners/me"),
  });
  const application = query.data?.find((item) =>
    ["DRAFT", "CORRECTION_REQUIRED"].includes(item.status),
  );
  if (!application) return null;

  async function upload(file: File) {
    const form = new FormData();
    form.set("profile_photo", file);
    const response = await fetch(`/api/practitioners/me/${application?.id}/profile-photo`, {
      method: "POST",
      body: form,
    });
    setMessage(response.ok ? "Professional photograph uploaded securely." : "Photograph upload failed.");
  }

  return (
    <section className="mt-5 rounded-2xl border bg-white p-5 sm:p-7">
      <h2 className="text-xl font-bold">Professional photograph</h2>
      <p className="mt-2 text-sm text-slate-600">
        Upload a clear JPEG or PNG profile photograph up to 5 MB. It is published only after approval.
      </p>
      <input
        aria-label="Professional profile photograph"
        type="file"
        accept=".jpg,.jpeg,.png"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void upload(file);
        }}
        className="mt-4 min-h-12 w-full rounded-xl border p-3 sm:max-w-lg"
      />
      {message && <p role="status" className="mt-3 text-sm text-slate-700">{message}</p>}
    </section>
  );
}
