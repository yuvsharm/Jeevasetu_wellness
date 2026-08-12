"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import type { PractitionerApplication } from "@/lib/practitioners/contracts";

type Config = { kind: string; label: string; required: boolean };
const size = (bytes: number) => bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

function FilenamePreview({ documentId, title }: { documentId: string; title: string }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [source, setSource] = useState("");
  const [error, setError] = useState("");
  useEffect(() => () => { if (source) URL.revokeObjectURL(source); }, [source]);

  async function open() {
    setError("");
    try {
      const response = await fetch(`/api/practitioners/documents/${documentId}`, { credentials: "same-origin" });
      if (!response.ok || response.headers.get("content-type")?.split(";", 1)[0].trim() !== "application/pdf") throw new Error();
      const blob = await response.blob();
      if (!blob.size) throw new Error();
      const next = URL.createObjectURL(blob);
      setSource((current) => { if (current) URL.revokeObjectURL(current); return next; });
      dialog.current?.showModal();
    } catch { setError("The document could not be opened. Please retry."); }
  }

  function close() {
    dialog.current?.close();
    setSource((current) => { if (current) URL.revokeObjectURL(current); return ""; });
  }

  return <>
    <button type="button" onClick={() => void open()} className="break-all text-left font-semibold text-emerald-800 underline underline-offset-2 hover:text-emerald-950 focus-visible:rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">{title}</button>
    {error && <span role="alert" className="block text-sm text-red-700">{error}</span>}
    <dialog ref={dialog} aria-label={title} className="m-auto h-[88vh] w-[94vw] max-w-5xl rounded-2xl p-0"><div className="flex h-full flex-col"><header className="flex items-center justify-between gap-3 border-b p-3"><b className="truncate">{title}</b><button type="button" onClick={close} className="min-h-11 rounded-xl border px-4">Close</button></header>{source && <iframe title={title} src={source} className="min-h-0 flex-1" />}</div></dialog>
  </>;
}

export function SecureDocumentCard({ application, config }: { application: PractitionerApplication; config: Config }) {
  const client = useQueryClient();
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const uploaded = application.documents.find((document) => document.kind === config.kind);

  async function upload(file: File) {
    if (file.type !== "application/pdf" || !file.name.toLowerCase().endsWith(".pdf")) { setMessage("Choose a PDF file."); return; }
    if (file.size > 8 * 1024 * 1024) { setMessage("Choose a PDF no larger than 8 MB."); return; }
    setBusy(true); setMessage("Uploading…");
    try {
      const form = new FormData(); form.set("kind", config.kind); form.set("file", file);
      const response = await fetch(`/api/practitioners/me/${application.id}/documents`, { method: "POST", body: form });
      if (!response.ok) throw new Error();
      setMessage("✓ Uploaded successfully");
      await client.invalidateQueries({ queryKey: ["my-practitioner-applications"] });
    } catch { setMessage("Upload failed. Check the PDF and retry."); }
    finally { setBusy(false); }
  }

  async function remove() {
    if (!uploaded || !window.confirm(`Remove ${config.label}?`)) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/practitioners/documents/${uploaded.id}`, { method: "DELETE" });
      if (!response.ok) throw new Error();
      setMessage("Document removed.");
      await client.invalidateQueries({ queryKey: ["my-practitioner-applications"] });
    } catch { setMessage("The document could not be removed. Please retry."); }
    finally { setBusy(false); }
  }

  return <article className="min-w-0 rounded-2xl border bg-white p-5">
    <h3 className="font-bold">{config.label} {config.required && <span className="text-red-700" aria-label="required">*</span>}</h3>
    <p className="mt-1 text-sm text-slate-600">{config.required ? "Required" : "Optional"} · PDF only · Maximum 8 MB</p>
    {uploaded && <div className="mt-4 flex min-w-0 items-start gap-2 rounded-xl bg-emerald-50 p-3"><span aria-hidden="true">✓</span><div className="min-w-0 flex-1"><FilenamePreview documentId={uploaded.id} title={uploaded.original_name} /><p className="text-xs text-slate-600">{size(uploaded.size_bytes)}</p></div><button type="button" title={`Remove ${config.label}`} aria-label={`Remove ${config.label}`} disabled={busy} onClick={() => void remove()} className="grid min-h-11 min-w-11 place-items-center text-xl text-red-700">🗑</button></div>}
    <label className="mt-4 inline-flex min-h-11 cursor-pointer items-center rounded-xl border border-emerald-700 px-4 font-bold text-emerald-800">{busy ? "Uploading…" : uploaded ? "Change PDF" : "Upload PDF"}<input disabled={busy} type="file" accept="application/pdf,.pdf" className="sr-only" onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file); event.currentTarget.value = ""; }} /></label>
    {message && <p role="status" className="mt-3 text-sm">{message}</p>}
  </article>;
}
