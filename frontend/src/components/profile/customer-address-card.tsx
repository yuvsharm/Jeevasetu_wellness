"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { AddressCapture } from "@/components/location/address-capture";
import { requestJson } from "@/lib/api/client";
import { emptyServiceAddress, type ServiceAddress } from "@/lib/location/contracts";

export function CustomerAddressCard() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["customer-profile"],
    queryFn: () => requestJson<{ address: ServiceAddress | null }>("/api/customer/profile"),
  });
  const [editing, setEditing] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [message, setMessage] = useState("");
  const [address, setAddress] = useState<ServiceAddress>(emptyServiceAddress());
  const save = useMutation({
    mutationFn: () => requestJson("/api/customer/profile", { method: "PATCH", body: JSON.stringify(address) }),
    onSuccess: async () => {
      setEditing(false);
      setConfirmed(false);
      setMessage("Primary service address updated.");
      await client.invalidateQueries({ queryKey: ["customer-profile"] });
    },
  });

  if (query.isPending) return null;
  const toggleEditing = () => {
    if (!editing) setAddress(query.data?.address ?? emptyServiceAddress());
    setEditing((value) => !value);
    setConfirmed(false);
  };

  return <section className="mb-6 min-w-0 rounded-2xl border bg-white p-4 sm:p-6">
    <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
      <div className="min-w-0">
        <h2 className="text-xl font-bold">Primary Service Address</h2>
        <p className="mt-1 text-sm text-slate-600">Used by default for new bookings. Your coordinates remain private.</p>
      </div>
      <button type="button" className="button-secondary" onClick={toggleEditing}>{editing ? "Cancel" : "Edit Address"}</button>
    </div>
    {message && <p role="status" className="mt-3 rounded-xl bg-emerald-50 p-3 text-emerald-900">{message}</p>}
    {editing ? <div className="mt-4 min-w-0">
      <AddressCapture value={address} onChange={setAddress} title="Primary Service Address" onConfirmedChange={setConfirmed} />
      <button type="button" disabled={!confirmed || save.isPending} onClick={() => save.mutate()} className="button-primary mt-4 disabled:opacity-50">{save.isPending ? "Saving…" : "Save Confirmed Address"}</button>
      {save.error && <p role="alert" className="mt-3 text-red-700">{save.error.message}</p>}
    </div> : query.data?.address ? <p className="mt-4 break-words">{query.data.address.address_line_1}, {query.data.address.city}, {query.data.address.region} {query.data.address.pin_code}</p> : <p className="mt-4 text-amber-800">No primary address is available.</p>}
  </section>;
}
