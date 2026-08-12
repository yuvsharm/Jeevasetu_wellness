"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";

import { ClientApiError, requestJson } from "@/lib/api/client";
import type { TherapyOption } from "@/lib/appointments/contracts";
import type { PractitionerApplication } from "@/lib/practitioners/contracts";
import { SecureDocumentCard } from "@/components/practitioners/secure-document-card";

const steps = [
  "Personal",
  "Professional",
  "Experience",
  "Service",
  "Documents",
  "Review",
];
const initial: Record<string, unknown> = {
  category: "PHYSIOTHERAPIST",
  full_legal_name: "",
  date_of_birth: null,
  gender: "PREFER_NOT_TO_SAY",
  mobile_number: "",
  alternate_mobile: "",
  email: "",
  current_address: "",
  city: "Meerut",
  state: "Uttar Pradesh",
  pin_code: "",
  highest_qualification: "BPT",
  specialization: "",
  college_institute: "",
  awarding_body: "",
  passing_year: null,
  registration_number: "",
  registration_authority: "",
  registration_expiry: null,
  experience_years: 0,
  experience_months: 0,
  recent_organization: "",
  previous_experience: "",
  has_home_service_experience: false,
  bio: "",
  languages: ["Hindi"],
  clinic: null,
  availability_notes: "",
  last_completed_step: 0,
};
const editableStatuses = ["DRAFT", "CORRECTION_REQUIRED"];

const documents = [
  {
    kind: "GOVERNMENT_ID",
    label: "Government identity proof",
    required: true,
    multiple: false,
  },
  {
    kind: "QUALIFICATION",
    label: "Highest qualification certificate",
    required: true,
    multiple: false,
  },
  {
    kind: "REGISTRATION",
    label: "Professional registration / licence certificate",
    required: false,
    multiple: false,
  },
  {
    kind: "TRAINING",
    label: "Specialization / additional training",
    required: false,
    multiple: false,
  },
] as const;

function payload(data: Record<string, unknown>, step: number) {
  const editable = Object.fromEntries(
    Object.keys(initial).map((key) => [key, data[key]]),
  );
  return {
    ...editable,
    date_of_birth: data.date_of_birth || null,
    passing_year: data.passing_year || null,
    registration_expiry: data.registration_expiry || null,
    languages: Array.isArray(data.languages)
      ? data.languages
      : String(data.languages || "")
          .split(",")
          .map((v) => v.trim())
          .filter(Boolean),
    last_completed_step: step,
  };
}

function friendly(value: unknown) {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.join(", ");
  return String(value ?? "Not provided")
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function fileSize(bytes: number) {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

async function photoErrorMessage(response: Response) {
  if (response.status === 401)
    return "Your session expired. Please sign in again.";
  if (response.status >= 500)
    return "We couldn't upload the photo right now. Please try again.";
  let detail = "";
  try {
    detail = JSON.stringify(await response.json()).toLowerCase();
  } catch {
    /* Use the safe format fallback. */
  }
  if (detail.includes("5 mb") || detail.includes("size"))
    return "Photo must be 5 MB or smaller.";
  if (
    detail.includes("invalid_image") ||
    detail.includes("corrupt") ||
    detail.includes("could not be read")
  )
    return "This image could not be read. Please choose another image.";
  return "Please choose a valid JPG, JPEG, PNG, or WebP image.";
}

function SecurePreview({
  url,
  title,
  label = "View document",
}: {
  url: string;
  title: string;
  label?: string;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [source, setSource] = useState("");
  const [error, setError] = useState("");
  useEffect(
    () => () => {
      if (source) URL.revokeObjectURL(source);
    },
    [source],
  );
  async function open() {
    setError("");
    try {
      const response = await fetch(url, { credentials: "same-origin" });
      if (!response.ok) throw new Error();
      const next = URL.createObjectURL(await response.blob());
      setSource((current) => {
        if (current) URL.revokeObjectURL(current);
        return next;
      });
      dialog.current?.showModal();
    } catch {
      setError("The document could not be opened. Please retry.");
    }
  }
  return (
    <>
      <button
        type="button"
        title={label}
        aria-label={label}
        onClick={() => void open()}
        className="grid min-h-11 min-w-11 place-items-center rounded-lg text-xl text-emerald-800"
      >
        👁
      </button>
      {error && (
        <span role="alert" className="text-sm text-red-700">
          {error}
        </span>
      )}
      <dialog
        ref={dialog}
        aria-label={title}
        className="m-auto h-[min(88vh,900px)] w-[min(94vw,1000px)] rounded-2xl border-0 p-0 shadow-2xl backdrop:bg-slate-950/60"
      >
        <div className="flex h-full min-h-0 flex-col bg-white">
          <header className="flex items-center justify-between gap-4 border-b px-4 py-3 sm:px-6">
            <h2 className="min-w-0 truncate font-bold">{title}</h2>
            <button
              type="button"
              autoFocus
              onClick={() => dialog.current?.close()}
              className="min-h-11 rounded-xl border px-4 font-bold"
            >
              Close
            </button>
          </header>
          {source && (
            <iframe
              title={title}
              src={source}
              className="min-h-0 flex-1 bg-slate-100"
            />
          )}
        </div>
      </dialog>
    </>
  );
}

export function EnrollmentForm() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["my-practitioner-applications"],
    queryFn: () =>
      requestJson<PractitionerApplication[]>("/api/practitioners/me"),
  });
  const application = query.data?.find(
    (item) => !["REJECTED", "WITHDRAWN"].includes(item.status),
  );
  const editable = application && editableStatuses.includes(application.status);
  const [data, setData] = useState<Record<string, unknown>>(initial);
  const [step, setStep] = useState(0);
  const [saveState, setSaveState] = useState<
    "idle" | "saving" | "saved" | "error"
  >("idle");
  const [dirty, setDirty] = useState(false);
  const hydrated = useRef<string | null>(null);
  const autosaveBlocked = useRef(false);

  const create = useMutation({
    mutationFn: () =>
      requestJson<PractitionerApplication>("/api/practitioners/me", {
        method: "POST",
        body: JSON.stringify({}),
      }),
    onSuccess: (item) =>
      client.setQueryData<PractitionerApplication[]>(
        ["my-practitioner-applications"],
        (old) => [item, ...(old ?? [])],
      ),
  });
  useEffect(() => {
    if (
      !query.isPending &&
      !application &&
      !create.isPending &&
      !create.isSuccess
    )
      create.mutate();
  }, [application, create, query.isPending]);
  useEffect(() => {
    if (application && hydrated.current !== application.id) {
      setData({ ...initial, ...application });
      setStep(Math.min(application.last_completed_step ?? 0, 5));
      hydrated.current = application.id;
    }
  }, [application]);

  const save = useMutation({
    mutationFn: async (nextStep: number) =>
      requestJson<PractitionerApplication>(
        `/api/practitioners/me/${application?.id}`,
        { method: "PATCH", body: JSON.stringify(payload(data, nextStep)) },
      ),
    retry: (failureCount, error) =>
      error instanceof ClientApiError &&
      error.status >= 500 &&
      failureCount < 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 4000),
    onMutate: () => setSaveState("saving"),
    onSuccess: (item) => {
      autosaveBlocked.current = false;
      setSaveState("saved");
      setDirty(false);
      client.setQueryData<PractitionerApplication[]>(
        ["my-practitioner-applications"],
        (old) => old?.map((v) => (v.id === item.id ? item : v)),
      );
    },
    onError: () => {
      autosaveBlocked.current = true;
      setSaveState("error");
    },
  });
  useEffect(() => {
    if (!editable || !dirty || autosaveBlocked.current) return;
    const timer = setTimeout(() => save.mutate(step), 1000);
    return () => clearTimeout(timer);
  }, [data, dirty, editable, save, step]);
  useEffect(() => {
    const onHide = () => {
      if (editable && dirty) save.mutate(step);
    };
    window.addEventListener("pagehide", onHide);
    return () => window.removeEventListener("pagehide", onHide);
  }, [dirty, editable, save, step]);

  function change(name: string, value: unknown) {
    autosaveBlocked.current = false;
    setData((current) => ({ ...current, [name]: value }));
    setDirty(true);
  }
  function retrySave() {
    autosaveBlocked.current = false;
    save.mutate(step);
  }
  function field(name: string, label: string, type = "text") {
    return (
      <label className="grid min-w-0 gap-2 font-semibold text-slate-800">
        {label}
        <input
          type={type}
          value={String(data[name] ?? "")}
          onChange={(e) =>
            change(
              name,
              type === "number"
                ? e.target.value
                  ? Number(e.target.value)
                  : null
                : e.target.value,
            )
          }
          className="min-h-12 min-w-0 rounded-xl border border-slate-300 px-4"
        />
      </label>
    );
  }
  function move(next: number) {
    if (editable && dirty) save.mutate(next);
    setStep(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  if (query.isPending || create.isPending)
    return (
      <p role="status" className="rounded-2xl border bg-white p-6">
        Preparing your secure draft…
      </p>
    );
  if (query.isError || create.isError)
    return (
      <p
        role="alert"
        className="rounded-2xl border border-red-200 bg-red-50 p-6 text-red-800"
      >
        We could not prepare your application. Please retry.
      </p>
    );
  if (application && !editable)
    return <SubmittedStatus application={application} />;
  if (!application) return null;

  const progress = Math.round(((step + 1) / steps.length) * 100);
  return (
    <section className="mx-auto min-w-0 max-w-6xl overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
      <header className="border-b bg-gradient-to-r from-emerald-950 to-emerald-800 p-5 text-white sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-bold uppercase tracking-[0.18em] text-emerald-200">
              Practitioner application
            </p>
            <h1 className="mt-2 text-2xl font-bold sm:text-3xl">
              Build your JeevaSetu practitioner profile
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-emerald-50">
              Your private draft is visible only to you and authorized
              reviewers.
            </p>
          </div>
          <SaveStatus state={saveState} retry={retrySave} />
        </div>
      </header>
      <div className="p-4 sm:p-7 lg:p-9">
        {application.correction_reason && (
          <p className="mt-4 rounded-xl bg-amber-50 p-4 text-amber-900">
            <strong>Correction requested:</strong>{" "}
            {application.correction_reason}
          </p>
        )}
        <div className="md:hidden" aria-live="polite">
          <div className="flex items-end justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-emerald-800">
                Step {step + 1} of 6
              </p>
              <p className="text-xl font-bold">{steps[step]}</p>
            </div>
            <p className="text-sm font-semibold">{progress}% complete</p>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200">
            <div
              className="h-full rounded-full bg-emerald-600 transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
        <ol
          className="hidden grid-cols-6 gap-2 md:grid"
          aria-label="Application progress"
        >
          {steps.map((label, index) => (
            <li key={label}>
              <button
                type="button"
                onClick={() => move(index)}
                aria-current={step === index ? "step" : undefined}
                className={`min-h-16 w-full rounded-xl border p-3 text-left text-xs font-bold ${step === index ? "border-emerald-700 bg-emerald-700 text-white" : index < step ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-slate-200 bg-white text-slate-500"}`}
              >
                <span aria-hidden="true">
                  {index < step ? "✓ " : `${index + 1}. `}
                </span>
                {label}
              </button>
            </li>
          ))}
        </ol>
        <div className="mt-8 min-w-0">
          {step === 0 && (
            <fieldset className="grid min-w-0 gap-5 sm:grid-cols-2">
              <legend className="mb-5 text-2xl font-bold">
                Personal details
              </legend>
              <div className="sm:col-span-2">
                <ProfilePhotoCard application={application} />
              </div>
              {field("full_legal_name", "Full legal name *")}
              {field("date_of_birth", "Date of birth *", "date")}
              <label className="grid gap-2 font-semibold">
                Gender
                <select
                  value={String(data.gender)}
                  onChange={(e) => change("gender", e.target.value)}
                  className="min-h-12 rounded-xl border px-4"
                >
                  <option value="FEMALE">Female</option>
                  <option value="MALE">Male</option>
                  <option value="OTHER">Other</option>
                  <option value="PREFER_NOT_TO_SAY">Prefer not to say</option>
                </select>
              </label>
              {field("mobile_number", "Mobile number *")}
              {field("alternate_mobile", "Alternate mobile (optional)")}
              {field("email", "Email *", "email")}
              <label className="grid gap-2 font-semibold">
                Languages
                <input
                  value={
                    Array.isArray(data.languages)
                      ? data.languages.join(", ")
                      : String(data.languages ?? "")
                  }
                  onChange={(e) =>
                    change(
                      "languages",
                      e.target.value
                        .split(",")
                        .map((v) => v.trim())
                        .filter(Boolean),
                    )
                  }
                  className="min-h-12 rounded-xl border px-4"
                />
                <span className="text-xs font-normal text-slate-500">
                  Separate languages with commas.
                </span>
              </label>
              <div className="sm:col-span-2">
                {field("current_address", "Current address *")}
              </div>
              {field("city", "City *")}
              {field("state", "State *")}
              {field("pin_code", "PIN code *")}
            </fieldset>
          )}
          {step === 1 && (
            <fieldset className="grid min-w-0 gap-5 sm:grid-cols-2">
              <legend className="mb-5 text-2xl font-bold">
                Professional qualification
              </legend>
              <label className="grid gap-2 font-semibold">
                Category
                <select
                  value={String(data.category)}
                  onChange={(e) => {
                    change("category", e.target.value);
                    change(
                      "highest_qualification",
                      e.target.value === "WELLNESS"
                        ? "WELLNESS_CERTIFICATION"
                        : "BPT",
                    );
                  }}
                  className="min-h-12 rounded-xl border px-4"
                >
                  <option value="PHYSIOTHERAPIST">Physiotherapist</option>
                  <option value="WELLNESS">
                    Naturopathy / wellness practitioner
                  </option>
                </select>
              </label>
              <label className="grid gap-2 font-semibold">
                Highest qualification
                <select
                  value={String(data.highest_qualification)}
                  onChange={(e) =>
                    change("highest_qualification", e.target.value)
                  }
                  className="min-h-12 rounded-xl border px-4"
                >
                  {data.category === "PHYSIOTHERAPIST" ? (
                    <>
                      <option>BPT</option>
                      <option>MPT</option>
                      <option>DPT</option>
                      <option value="OTHER_PHYSIOTHERAPY">
                        Other physiotherapy qualification
                      </option>
                    </>
                  ) : (
                    <option value="WELLNESS_CERTIFICATION">
                      Wellness qualification / certification
                    </option>
                  )}
                </select>
              </label>
              {field("specialization", "Specialization")}
              {field("college_institute", "College / institute")}
              {field("awarding_body", "University / awarding body")}
              {field("passing_year", "Passing year", "number")}
              {field(
                "registration_number",
                "Registration / licence number (where applicable)",
              )}
              {field("registration_authority", "Registration authority")}
              {field("registration_expiry", "Registration expiry", "date")}
            </fieldset>
          )}
          {step === 2 && (
            <fieldset className="grid min-w-0 gap-5 sm:grid-cols-2">
              <legend className="mb-5 text-2xl font-bold">
                Experience & expertise
              </legend>
              {field("experience_years", "Experience years *", "number")}
              {field("experience_months", "Additional months", "number")}
              {field("recent_organization", "Current / recent organization")}
              <label className="flex min-h-12 items-center gap-3 font-semibold">
                <input
                  type="checkbox"
                  checked={Boolean(data.has_home_service_experience)}
                  onChange={(e) =>
                    change("has_home_service_experience", e.target.checked)
                  }
                  className="size-5"
                />
                Home-service experience
              </label>
              <label className="grid gap-2 font-semibold sm:col-span-2">
                Previous relevant experience
                <textarea
                  value={String(data.previous_experience ?? "")}
                  onChange={(e) =>
                    change("previous_experience", e.target.value)
                  }
                  rows={4}
                  className="rounded-xl border p-4"
                />
              </label>
              <label className="grid gap-2 font-semibold sm:col-span-2">
                Professional bio *
                <textarea
                  value={String(data.bio ?? "")}
                  onChange={(e) => change("bio", e.target.value)}
                  rows={5}
                  className="rounded-xl border p-4"
                />
              </label>
              <Competencies application={application} />
            </fieldset>
          )}
          {step === 3 && (
            <fieldset className="grid gap-5 sm:grid-cols-2">
              <legend className="mb-5 text-2xl font-bold">
                Service & availability
              </legend>
              {field("city", "Primary service city *")}
              {field("pin_code", "Primary service PIN code *")}
              <label className="grid gap-2 font-semibold sm:col-span-2">
                Availability notes (optional)
                <textarea
                  value={String(data.availability_notes ?? "")}
                  onChange={(e) => change("availability_notes", e.target.value)}
                  rows={5}
                  placeholder="For example: Monday–Friday, 9 AM–6 PM; weekends by appointment."
                  className="rounded-xl border p-4"
                />
              </label>
            </fieldset>
          )}
          {step === 4 && <DocumentStep application={application} />}
          {step === 5 && (
            <Review application={application} data={data} edit={move} />
          )}
        </div>
        <div className="mt-8 flex flex-col-reverse gap-3 min-[390px]:flex-row min-[390px]:justify-between">
          {step > 0 ? (
            <button
              type="button"
              onClick={() => move(step - 1)}
              className="min-h-12 rounded-xl border px-5 font-bold"
            >
              Back
            </button>
          ) : (
            <span />
          )}
          {step < 5 && (
            <button
              type="button"
              onClick={() => move(step + 1)}
              className="min-h-12 rounded-xl bg-emerald-700 px-5 font-bold text-white"
            >
              Save and continue
            </button>
          )}
        </div>
      </div>
    </section>
  );
}

function SaveStatus({ state, retry }: { state: string; retry: () => void }) {
  if (state === "saving")
    return (
      <span
        role="status"
        className="rounded-full bg-white/15 px-4 py-2 text-sm text-white"
      >
        Saving…
      </span>
    );
  if (state === "saved")
    return (
      <span
        role="status"
        className="rounded-full bg-white/15 px-4 py-2 text-sm font-semibold text-white"
      >
        ✓ Saved just now
      </span>
    );
  if (state === "error")
    return (
      <button
        type="button"
        onClick={retry}
        className="min-h-11 rounded-full bg-red-50 px-4 text-sm font-semibold text-red-800"
      >
        Save failed — Retry
      </button>
    );
  return (
    <span className="rounded-full bg-white/15 px-4 py-2 text-sm text-white">
      Autosave ready
    </span>
  );
}

function Competencies({
  application,
}: {
  application: PractitionerApplication;
}) {
  const client = useQueryClient();
  const therapies = useQuery({
    queryKey: ["appointment-therapies"],
    queryFn: () => requestJson<TherapyOption[]>("/api/appointment-therapies"),
  });
  const add = useMutation({
    mutationFn: (therapy: string) =>
      requestJson(`/api/practitioners/me/${application.id}/competencies`, {
        method: "POST",
        body: JSON.stringify({ therapy, experience_months: 0 }),
      }),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["my-practitioner-applications"] }),
  });
  return (
    <div className="sm:col-span-2">
      <label className="grid gap-2 font-semibold">
        Service expertise
        <select
          aria-label="Add service expertise"
          defaultValue=""
          onChange={(e) => e.target.value && add.mutate(e.target.value)}
          className="min-h-12 rounded-xl border px-4"
        >
          <option value="">Select a service</option>
          {therapies.data
            ?.filter(
              (t) => !application.competencies.some((c) => c.therapy === t.id),
            )
            .map((t) => (
              <option value={t.id} key={t.id}>
                {t.name}
              </option>
            ))}
        </select>
      </label>
      <ul className="mt-3 text-sm text-slate-600">
        {application.competencies.map((item) => (
          <li key={item.id}>
            {item.therapy_name} · {friendly(item.verification_status)}
          </li>
        ))}
      </ul>
    </div>
  );
}

function DocumentStep({
  application,
}: {
  application: PractitionerApplication;
}) {
  return (
    <div>
      <h2 className="text-2xl font-bold">Documents</h2>
      <p className="mt-2 max-w-3xl text-slate-600">
        Upload clear PDF copies for verification. Every file stays private and
        can be previewed before you submit.
      </p>
      <div className="mt-5 grid min-w-0 gap-4 md:grid-cols-2">
        {documents.map((config) => (
          <SecureDocumentCard
            key={config.kind}
            application={application}
            config={config}
          />
        ))}
      </div>
    </div>
  );
}

function ProfilePhotoCard({
  application,
}: {
  application: PractitionerApplication;
}) {
  const client = useQueryClient();
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(
    application.has_profile_photo
      ? `/api/practitioners/me/${application.id}/profile-photo`
      : "",
  );
  async function upload(file: File) {
    if (file.size > 5 * 1024 * 1024) {
      setMessage("Photo must be 5 MB or smaller.");
      return;
    }
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      setMessage("Please choose a valid JPG, JPEG, PNG, or WebP image.");
      return;
    }
    setBusy(true);
    setMessage("Uploading…");
    try {
      const form = new FormData();
      form.set("profile_photo", file);
      const response = await fetch(
        `/api/practitioners/me/${application.id}/profile-photo`,
        { method: "POST", body: form },
      );
      if (response.ok) {
        setPreview(URL.createObjectURL(file));
        setMessage("✓ Uploaded successfully");
        void client.invalidateQueries({
          queryKey: ["my-practitioner-applications"],
        });
      } else {
        setMessage(await photoErrorMessage(response));
        if (response.status === 401)
          window.location.assign(
            "/login?reason=expired&returnTo=%2Fpractitioner-application",
          );
      }
    } catch {
      setMessage("Connection problem. Please try again.");
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    setBusy(true);
    const response = await fetch(
      `/api/practitioners/me/${application.id}/profile-photo`,
      { method: "DELETE" },
    );
    if (response.ok) {
      setPreview("");
      setMessage("Photo removed.");
      void client.invalidateQueries({
        queryKey: ["my-practitioner-applications"],
      });
    } else setMessage("The photo could not be removed. Retry.");
    setBusy(false);
  }
  return (
    <article className="overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <div className="relative size-28 shrink-0 overflow-hidden rounded-2xl bg-white ring-1 ring-slate-200">
          {preview ? (
            <Image
              unoptimized
              fill
              sizes="112px"
              src={preview}
              alt="Uploaded profile photo thumbnail"
              className="object-cover"
            />
          ) : (
            <span className="grid size-full place-items-center text-center text-xs text-slate-500">
              Add a clear
              <br />
              profile photo
            </span>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="font-bold">
            Profile photo{" "}
            <span className="text-red-700" aria-label="required">
              *
            </span>
          </h3>
          <p className="text-sm text-slate-600">
            JPG, JPEG, PNG, or WebP · Maximum 5 MB
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <label className="inline-flex min-h-11 cursor-pointer items-center rounded-xl bg-emerald-700 px-4 font-bold text-white">
              {busy ? "Uploading…" : preview ? "Replace" : "Upload photo"}
              <input
                disabled={busy}
                type="file"
                accept=".jpg,.jpeg,.png,.webp"
                className="sr-only"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void upload(file);
                }}
              />
            </label>
            {preview && (
              <>
                <SecurePreview
                  url={preview}
                  title="Profile photo"
                  label="View photo"
                />
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void remove()}
                  className="min-h-11 px-3 font-bold text-red-700"
                >
                  Remove
                </button>
              </>
            )}
          </div>
        </div>
      </div>
      {message && (
        <p role="status" className="mt-3 text-sm font-medium text-slate-700">
          {message}
        </p>
      )}
    </article>
  );
}

// Kept temporarily for compatibility with pending hydrated clients during this correction deploy.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function DocumentCard({
  application,
  config,
}: {
  application: PractitionerApplication;
  config: (typeof documents)[number];
}) {
  const client = useQueryClient();
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const uploaded = application.documents.filter(
    (doc) => doc.kind === config.kind,
  );
  async function upload(file: File) {
    if (
      file.type !== "application/pdf" ||
      !file.name.toLowerCase().endsWith(".pdf")
    ) {
      setMessage("Choose a PDF file.");
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      setMessage("Choose a PDF no larger than 8 MB.");
      return;
    }
    setBusy(true);
    setMessage("Uploading…");
    const form = new FormData();
    form.set("kind", config.kind);
    form.set("file", file);
    const response = await fetch(
      `/api/practitioners/me/${application.id}/documents`,
      { method: "POST", body: form },
    );
    setMessage(
      response.ok
        ? "✓ Uploaded successfully"
        : "Upload failed — check the PDF format and size, then retry.",
    );
    if (response.ok)
      void client.invalidateQueries({
        queryKey: ["my-practitioner-applications"],
      });
    setBusy(false);
  }
  async function remove(id: string) {
    setBusy(true);
    const response = await fetch(
      `/api/practitioners/me/${application.id}/documents/${id}`,
      { method: "DELETE" },
    );
    if (response.ok) {
      setMessage("Document removed.");
      void client.invalidateQueries({
        queryKey: ["my-practitioner-applications"],
      });
    } else setMessage("The document could not be removed. Retry.");
    setBusy(false);
  }
  return (
    <article className="min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="font-bold">
        {config.label}{" "}
        {config.required && (
          <span className="text-red-700" aria-label="required">
            *
          </span>
        )}
      </h3>
      <p className="mt-1 text-sm text-slate-600">
        {config.required ? "Required" : "Optional"} · PDF only · Maximum 8 MB
      </p>
      <label className="mt-4 inline-flex min-h-11 cursor-pointer items-center rounded-xl border border-emerald-700 px-4 font-bold text-emerald-800">
        {busy
          ? "Uploading…"
          : uploaded.length && !config.multiple
            ? "Replace PDF"
            : "Upload PDF"}
        <input
          disabled={busy}
          type="file"
          accept="application/pdf,.pdf"
          multiple={config.multiple}
          className="sr-only"
          onChange={(e) =>
            Array.from(e.target.files ?? []).forEach(
              (file) => void upload(file),
            )
          }
        />
      </label>
      <ul className="mt-4 grid gap-3">
        {uploaded.map((doc) => (
          <li
            key={doc.id}
            className="min-w-0 rounded-xl bg-emerald-50 p-3 text-sm"
          >
            <div className="flex min-w-0 items-start gap-2">
              <span aria-hidden="true" className="font-bold text-emerald-700">
                ✓
              </span>
              <div className="min-w-0">
                <p className="break-all font-semibold">{doc.original_name}</p>
                <p className="text-xs text-slate-600">
                  {config.label} · {fileSize(doc.size_bytes)}
                </p>
              </div>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-1">
              <SecurePreview
                url={`/api/practitioners/me/${application.id}/documents/${doc.id}`}
                title={doc.original_name}
              />
              <label className="inline-flex min-h-11 cursor-pointer items-center px-3 font-bold text-emerald-800 underline">
                Replace
                <input
                  disabled={busy}
                  type="file"
                  accept="application/pdf,.pdf"
                  className="sr-only"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) void upload(file);
                  }}
                />
              </label>
              <button
                type="button"
                disabled={busy}
                onClick={() => void remove(doc.id)}
                className="min-h-11 px-3 font-bold text-red-700"
              >
                Remove
              </button>
            </div>
          </li>
        ))}
      </ul>
      {message && (
        <p role="status" className="mt-3 text-sm font-medium text-slate-700">
          {message}
        </p>
      )}
    </article>
  );
}

const sections = [
  {
    title: "Personal details",
    step: 0,
    keys: [
      ["Full legal name", "full_legal_name"],
      ["Date of birth", "date_of_birth"],
      ["Mobile number", "mobile_number"],
      ["Email", "email"],
      ["Languages", "languages"],
      ["Address", "current_address"],
    ],
  },
  {
    title: "Professional details",
    step: 1,
    keys: [
      ["Category", "category"],
      ["Highest qualification", "highest_qualification"],
      ["Specialization", "specialization"],
      ["College / institute", "college_institute"],
      ["Awarding body", "awarding_body"],
      ["Passing year", "passing_year"],
    ],
  },
  {
    title: "Experience",
    step: 2,
    keys: [
      ["Experience years", "experience_years"],
      ["Home-service experience", "has_home_service_experience"],
      ["Professional bio", "bio"],
    ],
  },
  {
    title: "Service & availability",
    step: 3,
    keys: [
      ["City", "city"],
      ["PIN code", "pin_code"],
      ["Availability", "availability_notes"],
    ],
  },
] as const;
function Review({
  application,
  data,
  edit,
}: {
  application: PractitionerApplication;
  data: Record<string, unknown>;
  edit: (step: number) => void;
}) {
  const client = useQueryClient();
  const [serverMissing, setServerMissing] = useState<
    Array<{ section: string; code: string; label: string }>
  >([]);
  const submit = useMutation({
    mutationFn: async () => {
      setServerMissing([]);
      const response = await fetch(`/api/practitioners/me/${application.id}/submit`, {
        method: "POST",
      });
      const body = await response.json();
      if (!response.ok) {
        setServerMissing(Array.isArray(body.missing_requirements) ? body.missing_requirements : []);
        throw new Error(body.detail || "Submission could not be completed.");
      }
      return body as PractitionerApplication;
    },
    onSuccess: (submitted) =>
      client.setQueryData<PractitionerApplication[]>(["my-practitioner-applications"], (current) =>
        current?.map((item) => (item.id === submitted.id ? submitted : item)),
      ),
  });
  const missing = [] as string[];
  if (!application.has_profile_photo) missing.push("Personal: profile photo");
  for (const kind of ["GOVERNMENT_ID", "QUALIFICATION"])
    if (!application.documents.some((doc) => doc.kind === kind))
      missing.push(
        kind === "GOVERNMENT_ID"
          ? "Documents: government identity proof"
          : "Documents: qualification certificate",
      );
  if (
    data.registration_number &&
    !application.documents.some((doc) => doc.kind === "REGISTRATION")
  )
    missing.push("Documents: registration / licence certificate");
  return (
    <div>
      <h2 className="text-2xl font-bold">Review & submit</h2>
      <p className="mt-2 text-slate-600">
        Confirm your details and open every document you want to verify before
        submission.
      </p>
      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        {sections.map((section) => (
          <article
            key={section.title}
            className="rounded-2xl border border-slate-200 bg-slate-50 p-5"
          >
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-bold uppercase tracking-wide text-slate-700">
                {section.title}
              </h3>
              <button
                type="button"
                onClick={() => edit(section.step)}
                className="min-h-11 text-sm font-bold text-emerald-800 underline"
              >
                Edit
              </button>
            </div>
            <dl className="mt-3 grid gap-3 text-sm">
              {section.keys.map(([label, key]) => (
                <div key={key}>
                  <dt className="font-semibold text-slate-600">{label}</dt>
                  <dd className="break-words">{friendly(data[key])}</dd>
                </div>
              ))}
            </dl>
          </article>
        ))}
        <article className="rounded-2xl border border-slate-200 bg-slate-50 p-5 lg:col-span-2">
          <div className="flex items-center justify-between">
            <h3 className="font-bold uppercase tracking-wide text-slate-700">
              Documents
            </h3>
            <button
              type="button"
              onClick={() => edit(4)}
              className="min-h-11 text-sm font-bold text-emerald-800 underline"
            >
              Edit documents
            </button>
          </div>
          <ul className="mt-3 grid gap-3 md:grid-cols-2">
            {application.documents.map((doc) => (
              <li key={doc.id} className="rounded-xl bg-white p-3 text-sm">
                <p className="break-all font-semibold">✓ {doc.original_name}</p>
                <p className="text-xs text-slate-600">
                  {friendly(doc.kind)} · {fileSize(doc.size_bytes)}
                </p>
                <SecurePreview
                  url={`/api/practitioners/me/${application.id}/documents/${doc.id}`}
                  title={doc.original_name}
                />
              </li>
            ))}
          </ul>
        </article>
      </div>
      {missing.length > 0 && (
        <div
          role="alert"
          className="mt-5 rounded-xl bg-amber-50 p-4 text-amber-900"
        >
          <strong>Complete these sections before submission:</strong>
          <ul className="mt-2 list-disc pl-5">
            {missing.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <button
            type="button"
            onClick={() => edit(missing[0].startsWith("Personal") ? 0 : 4)}
            className="mt-2 min-h-11 font-bold underline"
          >
            Fix incomplete section
          </button>
        </div>
      )}
      {submit.isError && (
        <div role="alert" className="mt-4 rounded-xl bg-red-50 p-4 text-red-800">
          <strong>Please complete the following before submitting:</strong>
          {serverMissing.length ? <div className="mt-3 grid gap-3">{Object.entries(Object.groupBy(serverMissing, item=>item.section)).map(([section,items])=><section key={section}><h3 className="font-bold">{friendly(section)}</h3><ul className="list-disc pl-5">{items?.map(item=><li key={item.code}>{item.label}</li>)}</ul><button type="button" onClick={()=>edit(section==="documents"?4:section==="service_availability"?3:section==="professional_details"?1:0)} className="mt-1 min-h-11 font-bold underline">Go to {section==="documents"?"Documents":friendly(section)}</button></section>)}</div>:<p className="mt-2">{submit.error.message} Your draft remains saved.</p>}
        </div>
      )}
      <div className="mt-6 rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
        <p className="text-sm text-emerald-950">
          Submitting sends this application and its private documents to
          JeevaSetu for verification. Operational access is granted only after
          approval.
        </p>
        <div className="mt-4 flex flex-col gap-3 sm:flex-row">
          <button
            type="button"
            disabled={submit.isPending}
            onClick={() => submit.mutate()}
            className="min-h-12 rounded-xl bg-emerald-700 px-5 font-bold text-white disabled:opacity-50"
          >
            {submit.isPending ? "Submitting…" : "Submit application"}
          </button>
          <button
            type="button"
            onClick={() => edit(4)}
            className="min-h-12 rounded-xl border border-emerald-700 px-5 font-bold text-emerald-800"
          >
            Save draft
          </button>
        </div>
      </div>
    </div>
  );
}

function SubmittedStatus({
  application,
}: {
  application: PractitionerApplication;
}) {
  const title =
    application.status === "APPROVED"
      ? "Application approved"
      : ["SUBMITTED", "RESUBMITTED"].includes(application.status)
        ? "Application submitted successfully"
        : "Application status";
  return (
    <section className="mx-auto max-w-5xl overflow-hidden rounded-3xl border bg-white shadow-sm">
      <div className="bg-emerald-900 p-6 text-white sm:p-9">
        <p className="text-sm font-bold uppercase tracking-widest text-emerald-200">
          Practitioner enrollment
        </p>
        <h1 className="mt-2 text-3xl font-bold">{title}</h1>
        <p className="mt-3 text-emerald-50">
          Thank you. Your application is securely saved and is now available to
          JeevaSetu reviewers.
        </p>
      </div>
      <div className="p-6 sm:p-9">
        <dl className="grid gap-4 rounded-2xl bg-slate-50 p-5 sm:grid-cols-3">
          <div>
            <dt className="text-sm font-semibold text-slate-600">
              Reference number
            </dt>
            <dd className="mt-1 break-all font-bold">{application.id}</dd>
          </div>
          <div>
            <dt className="text-sm font-semibold text-slate-600">Submitted</dt>
            <dd className="mt-1 font-bold">
              {application.submitted_at
                ? new Date(application.submitted_at).toLocaleString()
                : "Saved"}
            </dd>
          </div>
          <div>
            <dt className="text-sm font-semibold text-slate-600">
              Current status
            </dt>
            <dd className="mt-1 font-bold text-emerald-800">
              {friendly(application.status)}
            </dd>
          </div>
        </dl>
        <h2 className="mt-7 text-xl font-bold">What happens next</h2>
        <p className="mt-2 text-slate-600">
          The team will verify your details and documents. If a correction is
          needed, you can return here, update the requested section, and
          resubmit. Operational access is granted only after approval.
        </p>
        <article
          id="application-details"
          className="mt-7 scroll-mt-6 rounded-2xl border bg-slate-50 p-5"
        >
          <h2 className="text-xl font-bold">Application details</h2>
          <dl className="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <dt className="text-sm font-semibold text-slate-600">
                Applicant
              </dt>
              <dd>{application.full_legal_name}</dd>
            </div>
            <div>
              <dt className="text-sm font-semibold text-slate-600">Category</dt>
              <dd>{friendly(application.category)}</dd>
            </div>
            <div>
              <dt className="text-sm font-semibold text-slate-600">
                Qualification
              </dt>
              <dd>{friendly(application.highest_qualification)}</dd>
            </div>
            <div>
              <dt className="text-sm font-semibold text-slate-600">
                Service area
              </dt>
              <dd>
                {application.city} {application.pin_code}
              </dd>
            </div>
          </dl>
        </article>
        <h2 className="mt-7 text-xl font-bold">Uploaded documents</h2>
        <ul className="mt-3 grid gap-3 md:grid-cols-2">
          {application.documents.map((doc) => (
            <li key={doc.id} className="rounded-xl border p-4">
              <p className="break-all font-semibold">✓ {doc.original_name}</p>
              <p className="text-sm text-slate-600">
                {friendly(doc.kind)} · {fileSize(doc.size_bytes)}
              </p>
              <SecurePreview
                url={`/api/practitioners/me/${application.id}/documents/${doc.id}`}
                title={doc.original_name}
              />
            </li>
          ))}
        </ul>
        <div className="mt-7 flex flex-col gap-3 sm:flex-row">
          <a
            href="#application-details"
            className="grid min-h-12 place-items-center rounded-xl bg-emerald-700 px-5 font-bold text-white"
          >
            View application
          </a>
          <a
            href="/practitioner-application"
            className="grid min-h-12 place-items-center rounded-xl border border-emerald-700 px-5 font-bold text-emerald-800"
          >
            Go to applicant dashboard
          </a>
        </div>
      </div>
    </section>
  );
}
