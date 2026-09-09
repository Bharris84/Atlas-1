"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ConfidenceBadge, StatusPill, VerdictBadge } from "@/components/Badges";
import { PageHeader } from "@/components/Shell";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { api } from "@/lib/api";
import { EMPTY, formatMoney, formatNumber, formatScore } from "@/lib/format";
import { STRATEGY_LABELS, type PropertySummary } from "@atlas/shared-types";

export default function PropertiesPage() {
  const [rows, setRows] = useState<PropertySummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [state, setState] = useState("");

  const load = () => {
    setError(null);
    api
      .listProperties({ search: search || undefined, state: state || undefined })
      .then(setRows)
      .catch((cause) =>
        setError(cause instanceof Error ? cause.message : "Could not load properties.")
      );
  };

  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, state]);

  return (
    <>
      <PageHeader
        title="Properties"
        description="Everything under consideration, with the verdict from each property's most recent analysis."
        actions={
          <Link href="/properties/new" className="btn-primary">
            Add property
          </Link>
        }
      />

      <div className="mb-4 flex flex-wrap gap-2">
        <input
          className="input max-w-xs"
          placeholder="Search address or city"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          aria-label="Search properties"
        />
        <input
          className="input w-28"
          placeholder="State"
          maxLength={2}
          value={state}
          onChange={(event) => setState(event.target.value.toUpperCase())}
          aria-label="Filter by state"
        />
      </div>

      {error ? (
        <ErrorState message={error} onRetry={load} />
      ) : !rows ? (
        <LoadingState label="Loading properties…" />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No properties match"
          description="Add a property, or clear the filters above."
          action={
            <Link href="/properties/new" className="btn-primary">
              Add property
            </Link>
          }
        />
      ) : (
        <div className="card overflow-x-auto">
          <table className="table tabular min-w-[900px]">
            <thead>
              <tr>
                <th>Address</th>
                <th>Status</th>
                <th>Beds / baths</th>
                <th>Sq ft</th>
                <th>Verdict</th>
                <th>Score</th>
                <th>Strategy</th>
                <th>Profit</th>
                <th>Cash</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="hover:bg-ink-50">
                  <td>
                    <Link
                      href={`/properties/${row.id}`}
                      className="font-medium text-ink-900 hover:underline"
                    >
                      {row.address}
                    </Link>
                    <div className="text-xs text-ink-500">
                      {[row.city, row.state].filter(Boolean).join(", ") || EMPTY}
                    </div>
                  </td>
                  <td>
                    <StatusPill status={row.property_status} />
                  </td>
                  <td>
                    {row.bedrooms || row.bathrooms
                      ? `${formatNumber(row.bedrooms)} / ${formatNumber(row.bathrooms)}`
                      : EMPTY}
                  </td>
                  <td>{formatNumber(row.square_feet)}</td>
                  <td>
                    <VerdictBadge verdict={row.verdict} />
                  </td>
                  <td>{formatScore(row.deal_score)}</td>
                  <td>
                    {row.recommended_strategy
                      ? STRATEGY_LABELS[row.recommended_strategy]
                      : EMPTY}
                  </td>
                  <td>{formatMoney(row.profit)}</td>
                  <td>{formatMoney(row.cash_required)}</td>
                  <td>
                    <ConfidenceBadge confidence={row.confidence} label={false} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
