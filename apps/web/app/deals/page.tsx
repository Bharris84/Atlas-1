"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ConfidenceBadge, VerdictBadge } from "@/components/Badges";
import { PageHeader } from "@/components/Shell";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { api } from "@/lib/api";
import { EMPTY, formatMoney, formatScore } from "@/lib/format";
import { STRATEGY_LABELS, type PropertySummary } from "@atlas/shared-types";

/** Everything that has been underwritten, grouped by what the verdict says to do. */
export default function DealsPage() {
  const [rows, setRows] = useState<PropertySummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    api
      .listProperties()
      .then((properties) => setRows(properties.filter((p) => p.latest_analysis_id)))
      .catch((cause) =>
        setError(cause instanceof Error ? cause.message : "Could not load deals.")
      );
  };

  useEffect(load, []);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!rows) return <LoadingState />;

  const groups = [
    { verdict: "HUMAN_REVIEW_REQUIRED", title: "Human review required", caption: "A hard risk flag overrides the score on these." },
    { verdict: "PURSUE", title: "Pursue", caption: "Clears the buy box on a well-supported analysis." },
    { verdict: "INVESTIGATE", title: "Investigate", caption: "Worth more diligence, not yet worth an offer." },
    { verdict: "PASS", title: "Pass", caption: "Does not work at the price entered." },
  ] as const;

  return (
    <>
      <PageHeader
        title="Deals"
        description="Every property with a saved analysis, grouped by verdict."
      />

      {rows.length === 0 ? (
        <EmptyState
          title="Nothing analyzed yet"
          description="Underwrite a property and it will appear here."
          action={
            <Link href="/analyzer" className="btn-primary">
              Open the analyzer
            </Link>
          }
        />
      ) : (
        <div className="space-y-5">
          {groups.map((group) => {
            const matching = rows.filter((row) => row.verdict === group.verdict);
            if (matching.length === 0) return null;
            return (
              <div key={group.verdict} className="card">
                <div className="card-header">
                  <div>
                    <h2 className="card-title">{group.title}</h2>
                    <p className="text-xs text-ink-500">{group.caption}</p>
                  </div>
                  <span className="text-xs text-ink-500">{matching.length}</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="table tabular min-w-[720px]">
                    <thead>
                      <tr>
                        <th>Address</th>
                        <th>Strategy</th>
                        <th>Profit</th>
                        <th>Cash required</th>
                        <th>Score</th>
                        <th>Confidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {matching.map((row) => (
                        <tr key={row.id} className="hover:bg-ink-50">
                          <td>
                            <Link
                              href={`/properties/${row.id}`}
                              className="font-medium text-ink-900 hover:underline"
                            >
                              {row.address}
                            </Link>
                          </td>
                          <td>
                            {row.recommended_strategy
                              ? STRATEGY_LABELS[row.recommended_strategy]
                              : EMPTY}
                          </td>
                          <td>{formatMoney(row.profit)}</td>
                          <td>{formatMoney(row.cash_required)}</td>
                          <td>{formatScore(row.deal_score)}</td>
                          <td>
                            <ConfidenceBadge confidence={row.confidence} label={false} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}
