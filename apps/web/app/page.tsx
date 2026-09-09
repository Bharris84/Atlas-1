"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ConfidenceBadge, StatusPill, VerdictBadge } from "@/components/Badges";
import { PageHeader } from "@/components/Shell";
import { EmptyState, ErrorState, LoadingState, StatTile } from "@/components/States";
import { api } from "@/lib/api";
import {
  formatDateTime,
  formatMoney,
  formatMoneyCompact,
  formatScore,
  humanise,
} from "@/lib/format";
import { STRATEGY_LABELS, type Dashboard } from "@atlas/shared-types";

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    api
      .dashboard()
      .then(setData)
      .catch((cause) =>
        setError(cause instanceof Error ? cause.message : "Could not load the dashboard.")
      );
  };

  useEffect(load, []);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <LoadingState label="Loading dashboard…" />;

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Pipeline and projected economics across analyzed properties."
        actions={
          <>
            <Link href="/analyzer" className="btn-secondary">
              Analyze a deal
            </Link>
            <Link href="/properties/new" className="btn-primary">
              Add property
            </Link>
          </>
        }
      />

      {data.property_count === 0 ? (
        <EmptyState
          title="No properties yet"
          description="Add a property and enter what you know about it. Atlas will underwrite every strategy and tell you which one the numbers actually support."
          action={
            <Link href="/properties/new" className="btn-primary">
              Add your first property
            </Link>
          }
        />
      ) : (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile label="Properties" value={String(data.property_count)} />
            <StatTile
              label="Analyzed"
              value={String(data.analyzed_count)}
              hint="Latest analysis per property"
            />
            <StatTile
              label="Projected wholesale"
              value={formatMoneyCompact(data.projected_wholesale_revenue)}
              hint="Where wholesale is the recommended strategy"
            />
            <StatTile
              label="Projected flip profit"
              value={formatMoneyCompact(data.projected_flip_profit)}
              hint="Where flip is the recommended strategy"
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile
              label="Projected monthly cash flow"
              value={formatMoney(data.projected_monthly_cash_flow)}
              hint="Hold strategies only"
            />
            <StatTile
              label="Portfolio equity"
              value={formatMoneyCompact(data.portfolio_equity)}
              hint="Equity the recommended strategies would create"
            />
            <StatTile
              label="Needs human review"
              value={String(data.needs_human_review.length)}
              hint="Blocked by a hard risk flag"
            />
            <StatTile label="Follow-ups due" value={String(data.follow_ups.length)} />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <OpportunityList
              title="Top opportunities"
              caption="Highest deal score on the latest analysis."
              rows={data.top_opportunities}
              emptyText="No analyses yet."
            />
            <OpportunityList
              title="Needs human review"
              caption="A hard risk flag overrides the score on these."
              rows={data.needs_human_review}
              emptyText="Nothing is blocked on human review."
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="card">
              <div className="card-header">
                <h2 className="card-title">Pipeline</h2>
              </div>
              {data.pipeline.length === 0 ? (
                <p className="px-4 py-4 text-sm text-ink-500">Nothing in the pipeline.</p>
              ) : (
                <ul className="divide-y divide-ink-100">
                  {data.pipeline.map((bucket) => (
                    <li
                      key={bucket.status}
                      className="flex items-center justify-between px-4 py-2.5 text-sm"
                    >
                      <StatusPill status={bucket.status} />
                      <span className="tabular font-medium text-ink-900">
                        {bucket.count}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="card">
              <div className="card-header">
                <h2 className="card-title">Recent activity</h2>
              </div>
              {data.recent_activity.length === 0 ? (
                <p className="px-4 py-4 text-sm text-ink-500">No activity recorded.</p>
              ) : (
                <ul className="divide-y divide-ink-100">
                  {data.recent_activity.slice(0, 8).map((entry) => (
                    <li key={entry.id} className="px-4 py-2.5 text-sm">
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="text-ink-800">{humanise(entry.action)}</span>
                        <span className="whitespace-nowrap text-[11px] text-ink-400">
                          {formatDateTime(entry.occurred_at)}
                        </span>
                      </div>
                      {entry.summary && (
                        <p className="text-xs text-ink-500">{entry.summary}</p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {data.follow_ups.length > 0 && (
            <div className="card">
              <div className="card-header">
                <h2 className="card-title">Follow-ups</h2>
              </div>
              <ul className="divide-y divide-ink-100">
                {data.follow_ups.map((item) => (
                  <li key={item.id} className="flex justify-between px-4 py-2.5 text-sm">
                    <span className="text-ink-800">
                      {humanise(item.communication_type)}
                      {item.contact_name ? ` — ${item.contact_name}` : ""}
                    </span>
                    <span className="text-[11px] text-ink-500">
                      {formatDateTime(item.follow_up_at)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </>
  );
}

function OpportunityList({
  title,
  caption,
  rows,
  emptyText,
}: {
  title: string;
  caption: string;
  rows: Dashboard["top_opportunities"];
  emptyText: string;
}) {
  return (
    <div className="card">
      <div className="card-header">
        <h2 className="card-title">{title}</h2>
        <p className="text-xs text-ink-500">{caption}</p>
      </div>
      {rows.length === 0 ? (
        <p className="px-4 py-4 text-sm text-ink-500">{emptyText}</p>
      ) : (
        <ul className="divide-y divide-ink-100">
          {rows.map((row) => (
            <li key={row.id}>
              <Link
                href={`/properties/${row.id}`}
                className="block px-4 py-3 transition hover:bg-ink-50"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-ink-900">
                      {row.address}
                    </p>
                    <p className="text-xs text-ink-500">
                      {[row.city, row.state].filter(Boolean).join(", ")}
                      {row.recommended_strategy
                        ? ` · ${STRATEGY_LABELS[row.recommended_strategy]}`
                        : ""}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <VerdictBadge verdict={row.verdict} />
                    <span className="tabular text-xs text-ink-600">
                      Score {formatScore(row.deal_score)} · {formatMoney(row.profit)}
                    </span>
                    <ConfidenceBadge confidence={row.confidence} label={false} />
                  </div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
