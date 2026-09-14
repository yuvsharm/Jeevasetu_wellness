"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { isCompleteServiceAddress, type ReverseGeocodeResult, type ServiceAddress } from "@/lib/location/contracts";

type CaptureStatus = "idle" | "detecting" | "review" | "confirmed" | "error";
type AddressKey = "address_line_1" | "address_line_2" | "landmark" | "city" | "region" | "pin_code";
type RequiredAddressKey = "address_line_1" | "city" | "region" | "pin_code";
type LookupFailure = Error & { code?: string };

const addressKeys: AddressKey[] = ["address_line_1", "address_line_2", "landmark", "city", "region", "pin_code"];
const fieldClass = "min-h-12 w-full min-w-0 max-w-full rounded-xl border border-slate-300 bg-white px-4 font-normal text-slate-950 outline-none transition focus:border-emerald-700 focus:ring-4 focus:ring-emerald-100";

function hasUserAddress(value: ServiceAddress) {
  return Boolean(value.address_line_1.trim() || value.address_line_2.trim() || value.landmark.trim() || value.pin_code.trim());
}

function readableAddress(value: Pick<ServiceAddress, AddressKey>) {
  return addressKeys.map((key) => value[key].trim()).filter(Boolean).join(", ");
}

function missingRequired(value: ServiceAddress) {
  const missing = new Set<RequiredAddressKey>();
  if (!value.address_line_1.trim()) missing.add("address_line_1");
  if (!value.city.trim()) missing.add("city");
  if (!value.region.trim()) missing.add("region");
  if (!/^[1-9]\d{5}$/.test(value.pin_code.trim())) missing.add("pin_code");
  return missing;
}

function locationFailure(error: GeolocationPositionError) {
  if (error.code === error.PERMISSION_DENIED || error.code === 1) return "Location access was not allowed. Please enter your address manually.";
  return "We couldn't detect your location. Please try again or enter your address manually.";
}

function lookupFailure(error: unknown) {
  const code = error instanceof Error ? (error as LookupFailure).code : undefined;
  if (code === "NOT_CONFIGURED") return "We found your location, but automatic address lookup is not configured. Please complete it manually.";
  if (code === "RATE_LIMITED") return "We found your location, but address lookup is temporarily busy. Please complete it manually or try again later.";
  return "We found your location but couldn't identify the complete address. Please complete it manually.";
}

export function AddressCapture({ value, onChange, title = "Service address", onConfirmedChange, initiallyExpanded = true }:{
  value: ServiceAddress; onChange: (value: ServiceAddress) => void; title?: string;
  onConfirmedChange?: (confirmed: boolean) => void; initiallyExpanded?: boolean;
}) {
  const [status, setStatus] = useState<CaptureStatus>(initiallyExpanded ? "review" : "idle");
  const [message, setMessage] = useState("");
  const [detected, setDetected] = useState<ServiceAddress | null>(null);
  const [providerAddress, setProviderAddress] = useState("");
  const [missing, setMissing] = useState<Set<RequiredAddressKey>>(new Set());
  const valueRef = useRef(value);
  const requestGeneration = useRef(0);
  const locating = useRef(false);
  const houseInput = useRef<HTMLInputElement>(null);
  const displayedAddress = useMemo(() => readableAddress(value), [value]);
  const fieldsVisible = status !== "idle" || hasUserAddress(value);

  useEffect(() => { valueRef.current = value; }, [value]);
  useEffect(() => { onConfirmedChange?.(status === "confirmed"); }, [onConfirmedChange, status]);
  useEffect(() => () => { requestGeneration.current += 1; locating.current = false; }, []);

  const focusHouse = () => requestAnimationFrame(() => houseInput.current?.focus());

  const update = (name: AddressKey, next: string) => {
    requestGeneration.current += 1;
    locating.current = false;
    const normalized = name === "pin_code" ? next.replace(/\D/g, "").slice(0, 6) : next;
    const updated = { ...valueRef.current, [name]: normalized };
    valueRef.current = updated;
    onChange(updated);
    setMissing((current) => { const copy = new Set(current); copy.delete(name as RequiredAddressKey); return copy; });
    setDetected(null); setProviderAddress(""); setMessage(""); setStatus("review");
  };

  const manual = () => {
    requestGeneration.current += 1;
    locating.current = false;
    const updated = { ...valueRef.current, latitude: null, longitude: null, location_accuracy_meters: null, location_source: "MANUAL" as const };
    valueRef.current = updated;
    onChange(updated);
    setDetected(null); setProviderAddress(""); setMissing(new Set());
    setMessage("Enter your complete service address."); setStatus("review");
    focusHouse();
  };

  const locate = useCallback(() => {
    if (locating.current) return;
    if (typeof window !== "undefined" && !window.isSecureContext && window.location.hostname !== "localhost") {
      setMessage("We couldn't detect your location. Please try again or enter your address manually."); setStatus("error"); return;
    }
    if (!navigator.geolocation) {
      setMessage("We couldn't detect your location. Please try again or enter your address manually."); setStatus("error"); return;
    }
    locating.current = true;
    const generation = ++requestGeneration.current;
    setDetected(null); setProviderAddress(""); setMissing(new Set()); setMessage(""); setStatus("detecting");
    navigator.geolocation.getCurrentPosition(async ({ coords }) => {
      if (generation !== requestGeneration.current) return;
      const location = {
        latitude: Number(coords.latitude.toFixed(6)), longitude: Number(coords.longitude.toFixed(6)),
        location_accuracy_meters: Math.max(0, Math.round(coords.accuracy)), location_source: "DEVICE" as const,
      };
      try {
        const response = await fetch("/api/location/reverse-geocode", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(location),
        });
        const contentType = response.headers.get("content-type") ?? "";
        if (!contentType.includes("application/json")) throw new Error("invalid-response");
        const body = await response.json() as ReverseGeocodeResult & { code?: string };
        if (!response.ok) {
          const failure = new Error("lookup-failed") as LookupFailure;
          failure.code = typeof body.code === "string" ? body.code : undefined;
          throw failure;
        }
        if (generation !== requestGeneration.current) return;
        const current = valueRef.current;
        const resolved: ServiceAddress = {
          ...current,
          ...Object.fromEntries(addressKeys.map((key) => [key, String(body[key] ?? "")])),
          ...location,
        } as ServiceAddress;
        setProviderAddress(body.display_address || readableAddress(resolved));
        if (hasUserAddress(current)) {
          setDetected(resolved);
          setMessage("Review the detected details before replacing what you already entered.");
        } else {
          valueRef.current = resolved;
          onChange(resolved);
          setMessage(isCompleteServiceAddress(resolved)
            ? "Review the address and make any needed corrections."
            : "Please complete the missing required address details.");
        }
        setStatus("review");
      } catch (error) {
        if (generation !== requestGeneration.current) return;
        const current = valueRef.current;
        const updated = { ...current, ...location };
        valueRef.current = updated;
        onChange(updated);
        setMessage(lookupFailure(error));
        setStatus("error");
      } finally {
        if (generation === requestGeneration.current) locating.current = false;
      }
    }, (error) => {
      if (generation !== requestGeneration.current) return;
      locating.current = false;
      setMessage(locationFailure(error)); setStatus("error");
    }, { enableHighAccuracy: true, timeout: 12_000, maximumAge: 0 });
  }, [onChange]);

  const useDetected = () => {
    if (!detected) return;
    requestGeneration.current += 1;
    valueRef.current = detected;
    onChange(detected); setDetected(null);
    setMessage(isCompleteServiceAddress(detected)
      ? "Review the address and make any needed corrections."
      : "Please complete the missing required address details.");
    setStatus("review");
  };

  const confirm = () => {
    const invalid = missingRequired(valueRef.current);
    setMissing(invalid);
    if (invalid.size) {
      setStatus("error");
      setMessage("Complete the highlighted required fields before confirming.");
      if (invalid.has("address_line_1")) focusHouse();
      return;
    }
    const normalized = Object.fromEntries(addressKeys.map((key) => [key, valueRef.current[key].trim()]));
    const confirmed = { ...valueRef.current, ...normalized } as ServiceAddress;
    valueRef.current = confirmed;
    onChange(confirmed);
    setDetected(null); setProviderAddress(""); setMissing(new Set());
    setStatus("confirmed"); setMessage("Address confirmed.");
  };

  return <fieldset className="min-w-0 max-w-full rounded-2xl border border-slate-200 bg-slate-50/70 p-4 sm:p-5">
    <legend className="max-w-[calc(100%-1rem)] px-2 text-lg font-bold text-slate-950">{title}</legend>
    <div className="mt-1">
      <label htmlFor="service-address-search" className="sr-only">Search for area, street name, or landmark</label>
      <div className="relative"><span aria-hidden="true" className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400">⌕</span><input id="service-address-search" type="search" disabled placeholder="Search for area, street name, landmark..." className="min-h-12 w-full rounded-xl border border-slate-200 bg-slate-100 pl-11 pr-4 text-sm text-slate-500 placeholder:text-slate-500 disabled:cursor-not-allowed" aria-describedby="address-search-note"/></div>
      <p id="address-search-note" className="mt-1.5 text-xs text-slate-500">Address search is not available yet. Use your location or enter the address manually.</p>
    </div>
    <div className="mt-3 overflow-hidden rounded-xl border border-slate-200 bg-white">
      <button type="button" aria-label="Use your current location" className="flex min-h-16 w-full min-w-0 items-center gap-3 px-3 py-3 text-left transition hover:bg-emerald-50 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-inset focus-visible:ring-emerald-100 disabled:cursor-wait disabled:opacity-60 sm:px-4" disabled={status === "detecting"} onClick={locate}><span aria-hidden="true" className="grid size-9 shrink-0 place-items-center rounded-full bg-emerald-100 font-bold text-emerald-800">◎</span><span className="min-w-0 flex-1"><span className="block font-bold text-emerald-900">{status === "detecting" ? "Detecting your location..." : "Use your current location"}</span><span className="block text-xs text-slate-600">Detect location automatically</span></span><span aria-hidden="true" className="text-xl text-slate-400">›</span></button>
      <div className="mx-3 border-t border-slate-200 sm:mx-4"/>
      <button type="button" aria-label="Add address manually" className="flex min-h-16 w-full min-w-0 items-center gap-3 px-3 py-3 text-left transition hover:bg-emerald-50 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-inset focus-visible:ring-emerald-100 sm:px-4" onClick={manual}><span aria-hidden="true" className="grid size-9 shrink-0 place-items-center rounded-full bg-slate-100 text-xl font-bold text-slate-700">+</span><span className="min-w-0 flex-1"><span className="block font-bold text-slate-900">Add address manually</span><span className="block text-xs text-slate-600">Enter your complete service address</span></span><span aria-hidden="true" className="text-xl text-slate-400">›</span></button>
    </div>
    {status === "detecting" && <p role="status" aria-live="polite" className="mt-3 flex items-center rounded-xl border border-emerald-100 bg-white p-3 text-sm text-emerald-950"><span className="mr-2 inline-block size-4 animate-spin rounded-full border-2 border-emerald-700 border-t-transparent" aria-hidden="true"/>Detecting your location...</p>}
    {message && status !== "detecting" && <div role={status === "error" ? "alert" : "status"} aria-live="polite" className={`mt-3 rounded-xl border p-3 text-sm ${status === "error" ? "border-amber-200 bg-amber-50 text-amber-950" : status === "confirmed" ? "border-emerald-300 bg-emerald-50 text-emerald-950" : "border-emerald-200 bg-white text-slate-800"}`}>
      {value.location_source === "DEVICE" && providerAddress && <p className="font-bold text-emerald-900">Location detected</p>}<p className={providerAddress ? "mt-1" : "font-semibold"}>{message}</p>{providerAddress && <p className="mt-2 break-words font-medium">{providerAddress}</p>}{value.location_source === "DEVICE" && value.location_accuracy_meters != null && <p className="mt-1 text-xs text-slate-600">Approx. accuracy: {value.location_accuracy_meters} m</p>}{status === "confirmed" && displayedAddress && <p className="mt-2 break-words"><strong>Confirmed address:</strong> {displayedAddress}</p>}{providerAddress && <button type="button" className="mt-2 min-h-11 font-bold text-emerald-800 underline underline-offset-4" onClick={focusHouse}>Change</button>}
    </div>}
    {detected && <div className="mt-3 min-w-0 rounded-xl border border-emerald-200 bg-white p-3"><p className="break-words text-sm font-medium">{readableAddress(detected) || "Only a locality was returned."}</p><div className="mt-3 flex flex-wrap gap-2"><button type="button" className="button-primary" onClick={useDetected}>Use detected details</button><button type="button" className="button-secondary" onClick={() => { setDetected(null); setProviderAddress(""); setMessage("Your existing address was kept."); }}>Keep my entry</button></div></div>}
    {fieldsVisible && <><div className="mt-4 grid min-w-0 gap-4 md:grid-cols-2">
      <AddressField inputRef={houseInput} label="House / Flat / Building" name="address_line_1" value={value.address_line_1} update={update} invalid={missing.has("address_line_1")}/><AddressField label="Floor / Street / Locality (optional)" name="address_line_2" value={value.address_line_2} update={update}/><AddressField label="Landmark (optional)" name="landmark" value={value.landmark} update={update}/><AddressField label="City" name="city" value={value.city} update={update} invalid={missing.has("city")}/><AddressField label="State / Region" name="region" value={value.region} update={update} invalid={missing.has("region")}/><AddressField label="PIN code" name="pin_code" value={value.pin_code} update={update} maxLength={6} inputMode="numeric" invalid={missing.has("pin_code")}/>
    </div><button type="button" className="button-primary mt-4 w-full sm:w-auto" onClick={confirm}>Confirm this address</button></>}
  </fieldset>;
}

function AddressField({ label, name, value, update, maxLength, inputMode, invalid = false, inputRef }:{ label:string; name:AddressKey; value:string; update:(name:AddressKey,value:string)=>void; maxLength?:number; inputMode?:"numeric"; invalid?:boolean; inputRef?:React.RefObject<HTMLInputElement | null>; }) {
  const id = `address-${name}`;
  const errorId = `${id}-error`;
  return <label htmlFor={id} className="grid min-w-0 max-w-full gap-2 font-semibold leading-snug text-slate-800"><span className="min-w-0 break-words md:flex md:min-h-14 md:items-end">{label}</span><input ref={inputRef} id={id} className={`${fieldClass} ${invalid ? "border-red-500 focus:border-red-600 focus:ring-red-100" : ""}`} value={value} maxLength={maxLength} inputMode={inputMode} aria-invalid={invalid || undefined} aria-describedby={invalid ? errorId : undefined} autoComplete={name === "pin_code" ? "postal-code" : name === "region" ? "address-level1" : name === "city" ? "address-level2" : name === "address_line_1" ? "address-line1" : name === "address_line_2" ? "address-line2" : undefined} onChange={(event)=>update(name,event.target.value)} required={!label.includes("optional")}/>{invalid && <span id={errorId} className="text-sm font-normal text-red-700">{name === "pin_code" ? "Enter a valid 6-digit PIN code." : "This field is required."}</span>}</label>;
}
