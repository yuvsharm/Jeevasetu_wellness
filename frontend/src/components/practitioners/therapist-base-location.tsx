"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { AddressCapture } from "@/components/location/address-capture";
import { requestJson } from "@/lib/api/client";
import { emptyServiceAddress, type ServiceAddress } from "@/lib/location/contracts";

type PrivateLocation = {
  current_address: string;
  city: string;
  pin_code: string;
  base_latitude: number | null;
  base_longitude: number | null;
  base_location_accuracy_meters: number | null;
  base_location_source: "MANUAL" | "DEVICE";
};

function toAddress(value?: PrivateLocation): ServiceAddress {
  if (!value) return emptyServiceAddress();
  return {
    ...emptyServiceAddress(),
    address_line_1: value.current_address,
    city: value.city,
    region: "Uttar Pradesh",
    pin_code: value.pin_code,
    latitude: value.base_latitude,
    longitude: value.base_longitude,
    location_accuracy_meters: value.base_location_accuracy_meters,
    location_source: value.base_location_source,
  };
}

export function TherapistBaseLocation() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["staff-me"], queryFn: () => requestJson<PrivateLocation>("/api/staff/me") });
  const [editing, setEditing] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [message, setMessage] = useState("");
  const [address, setAddress] = useState<ServiceAddress>(emptyServiceAddress());
  const save = useMutation({
    mutationFn: () => requestJson("/api/staff/me", {
      method: "PATCH",
      body: JSON.stringify({
        current_address: [address.address_line_1, address.address_line_2, address.landmark].filter(Boolean).join(", "),
        city: address.city,
        pin_code: address.pin_code,
        base_latitude: address.latitude,
        base_longitude: address.longitude,
        base_location_accuracy_meters: address.location_accuracy_meters,
        base_location_source: address.location_source,
      }),
    }),
    onSuccess: async () => {
      setEditing(false);
      setConfirmed(false);
      setMessage("Base service location updated.");
      await client.invalidateQueries({ queryKey: ["staff-me"] });
    },
  });

  if (query.isPending) return null;
  const toggleEditing = () => {
    if (!editing) setAddress(toAddress(query.data));
    setEditing((value) => !value);
    setConfirmed(false);
  };

  return <section className="mb-6 min-w-0 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm sm:p-7">
    <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
      <div className="min-w-0">
        <h2 className="text-xl font-bold">Base Service Location</h2>
        <p className="mt-1 text-sm text-slate-600">Your exact address and coordinates are private and used only for service operations. Service Areas remain the separate authority for where you accept work.</p>
      </div>
      <button type="button" className="button-secondary" onClick={toggleEditing}>{editing ? "Cancel" : "Edit Address"}</button>
    </div>
    {message && <p role="status" className="mt-3 rounded-xl bg-emerald-50 p-3 text-emerald-900">{message}</p>}
    {editing ? <div className="mt-4 min-w-0">
      <AddressCapture value={address} onChange={setAddress} title="Therapist Base Address" onConfirmedChange={setConfirmed} />
      <button type="button" disabled={!confirmed || save.isPending} onClick={() => save.mutate()} className="button-primary mt-4 disabled:opacity-50">{save.isPending ? "Saving…" : "Save Confirmed Base Location"}</button>
      {save.error && <p role="alert" className="mt-3 text-red-700">{save.error.message}</p>}
    </div> : <p className="mt-4 break-words">{query.data?.current_address}, {query.data?.city} {query.data?.pin_code}</p>}
  </section>;
}
