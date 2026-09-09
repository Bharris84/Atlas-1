"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PageHeader } from "@/components/Shell";
import { api } from "@/lib/api";

const STATUSES = [
  "prospect",
  "analyzing",
  "offer_made",
  "under_contract",
  "closed",
  "rehabbing",
  "listed",
  "rented",
  "sold",
  "dead",
];

export default function NewPropertyPage() {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<Record<string, string>>({
    address: "",
    city: "",
    state: "",
    zip_code: "",
    county: "",
    property_type: "single_family",
    bedrooms: "",
    bathrooms: "",
    square_feet: "",
    lot_size: "",
    year_built: "",
    property_status: "prospect",
    listing_price: "",
    estimated_value: "",
    estimated_rent: "",
    notes: "",
  });

  const set = (key: string, value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      // Empty strings are omitted rather than sent: a blank field means
      // "unknown", and the API stores that as null, not zero.
      const payload: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(form)) {
        const trimmed = value.trim();
        if (trimmed === "") continue;
        payload[key] = key === "year_built" ? Number(trimmed) : trimmed;
      }
      const created = await api.createProperty(payload as never);
      router.push(`/properties/${created.id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not create the property.");
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Add property"
        description="Only the address is required. Anything you leave blank stays unknown rather than becoming zero."
      />

      <form onSubmit={submit} className="max-w-3xl space-y-4">
        <div className="card px-4 py-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Address" required value={form.address} onChange={(v) => set("address", v)} />
            <Field label="City" value={form.city} onChange={(v) => set("city", v)} />
            <Field
              label="State"
              maxLength={2}
              value={form.state}
              onChange={(v) => set("state", v.toUpperCase())}
            />
            <Field label="ZIP" value={form.zip_code} onChange={(v) => set("zip_code", v)} />
            <Field label="County" value={form.county} onChange={(v) => set("county", v)} />
            <div>
              <label className="label" htmlFor="property_type">
                Property type
              </label>
              <select
                id="property_type"
                className="input mt-1"
                value={form.property_type}
                onChange={(event) => set("property_type", event.target.value)}
              >
                <option value="single_family">Single family</option>
                <option value="multi_family">Multi family</option>
                <option value="condo">Condo</option>
                <option value="townhouse">Townhouse</option>
                <option value="manufactured">Manufactured</option>
                <option value="land">Land</option>
                <option value="commercial">Commercial</option>
              </select>
            </div>
          </div>
        </div>

        <div className="card px-4 py-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Bedrooms" value={form.bedrooms} onChange={(v) => set("bedrooms", v)} />
            <Field label="Bathrooms" value={form.bathrooms} onChange={(v) => set("bathrooms", v)} />
            <Field label="Square feet" value={form.square_feet} onChange={(v) => set("square_feet", v)} />
            <Field label="Lot size" value={form.lot_size} onChange={(v) => set("lot_size", v)} />
            <Field label="Year built" value={form.year_built} onChange={(v) => set("year_built", v)} />
            <div>
              <label className="label" htmlFor="property_status">
                Status
              </label>
              <select
                id="property_status"
                className="input mt-1"
                value={form.property_status}
                onChange={(event) => set("property_status", event.target.value)}
              >
                {STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {status.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>
            <Field label="Listing price" value={form.listing_price} onChange={(v) => set("listing_price", v)} />
            <Field label="Estimated value" value={form.estimated_value} onChange={(v) => set("estimated_value", v)} />
            <Field label="Estimated rent" value={form.estimated_rent} onChange={(v) => set("estimated_rent", v)} />
          </div>
          <div className="mt-3">
            <label className="label" htmlFor="notes">
              Notes
            </label>
            <textarea
              id="notes"
              className="input mt-1 min-h-[80px]"
              value={form.notes}
              onChange={(event) => set("notes", event.target.value)}
            />
          </div>
        </div>

        {error && <p className="text-sm text-fail-600">{error}</p>}

        <div className="flex gap-2">
          <button type="submit" className="btn-primary" disabled={saving || !form.address.trim()}>
            {saving ? "Creating…" : "Create property"}
          </button>
          <button type="button" className="btn-secondary" onClick={() => router.back()}>
            Cancel
          </button>
        </div>
      </form>
    </>
  );
}

function Field({
  label,
  value,
  onChange,
  required,
  maxLength,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  maxLength?: number;
}) {
  const id = label.toLowerCase().replace(/\s+/g, "_");
  return (
    <div>
      <label className="label" htmlFor={id}>
        {label}
        {required && <span className="text-fail-500"> *</span>}
      </label>
      <input
        id={id}
        className="input mt-1"
        value={value}
        maxLength={maxLength}
        required={required}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}
