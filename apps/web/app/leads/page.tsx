"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/Shell";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { api } from "@/lib/api";
import { formatDate, humanise } from "@/lib/format";
import type { Lead, LeadType, PropertySummary } from "@atlas/shared-types";

const LEAD_TYPES: LeadType[] = [
  "FSBO",
  "expired",
  "vacant",
  "absentee",
  "high_equity",
  "tax_delinquent",
  "probate",
  "code_violation",
  "pre_foreclosure",
  "tired_landlord",
  "price_reduction",
  "long_DOM",
  "off_market",
  "other",
];

const STATUSES = ["new", "contacted", "negotiating", "under_contract", "won", "lost", "dead"];

export default function LeadsPage() {
  const [leads, setLeads] = useState<Lead[] | null>(null);
  const [properties, setProperties] = useState<PropertySummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [form, setForm] = useState({ property_id: "", lead_type: "vacant", source: "" });

  const load = useCallback(() => {
    setError(null);
    api
      .listLeads({ lead_type: filter || undefined })
      .then(setLeads)
      .catch((cause) =>
        setError(cause instanceof Error ? cause.message : "Could not load leads.")
      );
  }, [filter]);

  useEffect(load, [load]);
  useEffect(() => {
    api.listProperties().then(setProperties).catch(() => setProperties([]));
  }, []);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (!form.property_id) return;
    await api.createLead({
      property_id: form.property_id,
      lead_type: form.lead_type as LeadType,
      source: form.source || null,
    });
    setForm({ ...form, source: "" });
    load();
  }

  const addressFor = (id: string) =>
    properties.find((property) => property.id === id)?.address ?? id;

  return (
    <>
      <PageHeader
        title="Leads"
        description="How a property came to attention. These are classifications of an observable situation — Atlas does not read them as evidence that an owner wants to sell."
      />

      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <form onSubmit={create} className="card h-fit px-4 py-4">
          <h2 className="card-title mb-3">Add a lead</h2>
          <div className="space-y-3">
            <div>
              <label className="label" htmlFor="lead-property">Property</label>
              <select
                id="lead-property"
                className="input mt-1"
                value={form.property_id}
                onChange={(event) => setForm({ ...form, property_id: event.target.value })}
              >
                <option value="">Select a property</option>
                {properties.map((property) => (
                  <option key={property.id} value={property.id}>
                    {property.address}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="lead-type">Lead type</label>
              <select
                id="lead-type"
                className="input mt-1"
                value={form.lead_type}
                onChange={(event) => setForm({ ...form, lead_type: event.target.value })}
              >
                {LEAD_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {humanise(type)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="lead-source">Source</label>
              <input
                id="lead-source"
                className="input mt-1"
                value={form.source}
                onChange={(event) => setForm({ ...form, source: event.target.value })}
              />
            </div>
            <button type="submit" className="btn-primary w-full" disabled={!form.property_id}>
              Add lead
            </button>
            {properties.length === 0 && (
              <p className="text-[11px] text-ink-500">
                <Link href="/properties/new" className="underline">
                  Add a property
                </Link>{" "}
                first — a lead is always attached to one.
              </p>
            )}
          </div>
        </form>

        <div>
          <div className="mb-3">
            <select
              className="input max-w-xs"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              aria-label="Filter by lead type"
            >
              <option value="">All lead types</option>
              {LEAD_TYPES.map((type) => (
                <option key={type} value={type}>
                  {humanise(type)}
                </option>
              ))}
            </select>
          </div>

          {error ? (
            <ErrorState message={error} onRetry={load} />
          ) : !leads ? (
            <LoadingState />
          ) : leads.length === 0 ? (
            <EmptyState
              title="No leads"
              description="Add one on the left, or clear the filter."
            />
          ) : (
            <div className="card overflow-x-auto">
              <table className="table min-w-[640px]">
                <thead>
                  <tr>
                    <th>Property</th>
                    <th>Type</th>
                    <th>Source</th>
                    <th>Status</th>
                    <th>Added</th>
                  </tr>
                </thead>
                <tbody>
                  {leads.map((lead) => (
                    <tr key={lead.id}>
                      <td>
                        <Link
                          href={`/properties/${lead.property_id}`}
                          className="font-medium text-ink-900 hover:underline"
                        >
                          {addressFor(lead.property_id)}
                        </Link>
                      </td>
                      <td>{humanise(lead.lead_type)}</td>
                      <td className="text-ink-600">{lead.source ?? "—"}</td>
                      <td>
                        <select
                          className="input py-1 text-xs"
                          value={lead.status}
                          onChange={async (event) => {
                            await api.updateLead(lead.id, { status: event.target.value });
                            load();
                          }}
                          aria-label={`Status for ${addressFor(lead.property_id)}`}
                        >
                          {STATUSES.map((status) => (
                            <option key={status} value={status}>
                              {humanise(status)}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="text-[11px] text-ink-500">
                        {formatDate(lead.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
