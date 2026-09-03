"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import type { PractitionerApplication } from "@/lib/practitioners/contracts";

const labels: Record<string, string> = { DRAFT:"Continue application", SUBMITTED:"View application status", UNDER_REVIEW:"View application status", CORRECTION_REQUIRED:"Update application" };

export function ApplicationCta() {
  const [application, setApplication] = useState<PractitionerApplication | null>(null);
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => {
    fetch("/api/practitioners/me", { cache:"no-store" })
      .then(response => { setSignedIn(response.ok); return response.ok ? response.json() : []; })
      .then((items: PractitionerApplication[]) => setApplication(items.find(item => !["REJECTED","WITHDRAWN"].includes(item.status)) ?? null))
      .catch(() => setApplication(null));
  }, []);
  const approved = application?.status === "APPROVED";
  const href = approved ? "/physiotherapist" : signedIn ? "/practitioner-application" : "/therapist-register";
  return <Link href={href} className="button-gold mt-7">{approved?"Go to practitioner dashboard":application?(labels[application.status]??"View application"):"Start application"}</Link>;
}
