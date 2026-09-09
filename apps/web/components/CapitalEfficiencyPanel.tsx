"use client";

import { useState } from "react";

import { ConfidenceBadge } from "@/components/Badges";
import { EMPTY, formatMoney, formatMonths, formatPercent, formatRatio, formatScore } from "@/lib/format";
import {
  STRATEGY_LABELS,
  STRATEGY_ORDER,
  type AnalysisResponse,
  type CapitalEfficiency,
  type StrategyKey,
} from "@atlas/shared-types";

/**
 * Capital efficiency, reported next to the ranking rather than folded into it.
 *
 * Two things this panel is careful about:
 *
 * 1. It shows the formula and the inputs, because a metric nobody can check by
 *    hand is a metric nobody should trust.
 * 2. It keeps efficiency and affordability visibly apart. A deal can be a
 *    superb use of capital and still be one you cannot fund, and collapsing
 *    those into one number would hide which problem you have.
 */
export function CapitalEfficiencyPanel({ analysis }: { analysis: AnalysisResponse }) {
  const metrics = analysis.capital_efficiency;
  const [open, setOpen] = useState<StrategyKey | null>(null);

  if (!metrics || Object.keys(metrics).length === 0) return null;

  const computable = STRATEGY_ORDER.filter((key) => metrics[key]?.computable);
  if (computable.length === 0) return null;

  return (
    <div className="card overflow-hidden">
      <div className="card-header">
        <div>
          <h2 className="card-title">
            Capital efficiency
            <span className="ml-2 rounded bg-ink-100 px-1.5 py-0.5 text-[10px] font-medium uppercase text-ink-500">
              provisional
            </span>
          </h2>
          <p className="mt-0.5 text-xs text-ink-500">
            How hard each dollar works, and how long it is stuck. Reported alongside the
            deal score — it does not change it.
          </p>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="table tabular min-w-[820px]" aria-label="Capital efficiency">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-white">Metric</th>
              {computable.map((key) => (
                <th key={key} className="min-w-[140px]">
                  <span className="text-sm font-semibold normal-case tracking-normal text-ink-900">
                    {STRATEGY_LABELS[key]}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <Row
              label="Capital deployed"
              keys={computable}
              metrics={metrics}
              render={(m) => formatMoney(m.capital_deployed)}
            />
            <Row
              label="Profit"
              keys={computable}
              metrics={metrics}
              render={(m) => formatMoney(m.profit)}
              hint="Exit profit for transactional strategies; annual cash flow for holds."
            />
            <Row
              label="Capital committed for"
              keys={computable}
              metrics={metrics}
              render={(m) => formatMonths(m.horizon_months)}
            />
            <Row
              label="Return on capital"
              keys={computable}
              metrics={metrics}
              render={(m) =>
                m.capital_free ? "no capital" : formatPercent(m.return_on_capital)
              }
            />
            <Row
              label="Turnover per year"
              keys={computable}
              metrics={metrics}
              render={(m) => (m.capital_velocity ? `${formatRatio(m.capital_velocity, 1)}x` : EMPTY)}
              hint="How many times a year this capital could be recycled."
            />
            <Row
              label="Annualised return"
              keys={computable}
              metrics={metrics}
              render={(m) =>
                m.capital_free ? "undefined" : formatPercent(m.annualized_return_on_capital)
              }
            />
            <Row
              label="Profit per $1k"
              keys={computable}
              metrics={metrics}
              render={(m) => formatMoney(m.profit_per_1k_deployed)}
            />
            <Row
              label="Efficiency score"
              keys={computable}
              metrics={metrics}
              render={(m) => formatScore(m.score)}
              hint="Hitting the target return scores 50; twice the target scores 100."
            />
            <Row
              label="Within capital limit"
              keys={computable}
              metrics={metrics}
              render={(m) => <AffordabilityCell metric={m} />}
              hint="Affordability, not efficiency. Blank when no investor profile is set."
            />
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap gap-2 border-t border-ink-200 px-4 py-3">
        {computable.map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setOpen(open === key ? null : key)}
            className={`rounded-md border px-2.5 py-1 text-xs font-medium transition ${
              open === key
                ? "border-ink-900 bg-ink-900 text-white"
                : "border-ink-300 bg-white text-ink-600 hover:bg-ink-100"
            }`}
          >
            How {STRATEGY_LABELS[key]} was computed
          </button>
        ))}
      </div>

      {open && <Working metric={metrics[open]} />}
    </div>
  );
}

function Row({
  label,
  keys,
  metrics,
  render,
  hint,
}: {
  label: string;
  keys: StrategyKey[];
  metrics: Record<StrategyKey, CapitalEfficiency>;
  render: (metric: CapitalEfficiency) => React.ReactNode;
  hint?: string;
}) {
  return (
    <tr>
      <td className="sticky left-0 z-10 whitespace-nowrap bg-white font-medium text-ink-600">
        <span
          title={hint}
          className={hint ? "cursor-help border-b border-dotted border-ink-300" : ""}
        >
          {label}
        </span>
      </td>
      {keys.map((key) => (
        <td key={key}>{render(metrics[key])}</td>
      ))}
    </tr>
  );
}

function AffordabilityCell({ metric }: { metric: CapitalEfficiency }) {
  if (metric.within_capital_limit === null) {
    return (
      <span className="text-xs text-ink-400" title="Set an investor profile in Settings.">
        not stated
      </span>
    );
  }
  return (
    <span
      className={`text-xs font-medium ${
        metric.within_capital_limit ? "text-pass-700" : "text-fail-600"
      }`}
    >
      {metric.within_capital_limit ? "Yes" : "Exceeds limit"}
      {metric.share_of_available_capital && (
        <span className="ml-1 font-normal text-ink-500">
          ({formatPercent(metric.share_of_available_capital, 0)} of capital)
        </span>
      )}
    </span>
  );
}

/** The working, so the number can be checked by hand. */
function Working({ metric }: { metric: CapitalEfficiency }) {
  return (
    <div className="border-t border-ink-200 bg-ink-50 px-4 py-4">
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <h4 className="label mb-1.5">How it is calculated</h4>
          <p className="text-sm text-ink-700">{metric.formula}</p>
          <div className="mt-3 flex items-center gap-2">
            <ConfidenceBadge confidence={metric.confidence} />
            <span className="text-[11px] text-ink-500">
              inherited from the figures this is built on
            </span>
          </div>
        </div>
        <div>
          <h4 className="label mb-1.5">Inputs used</h4>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
            {Object.entries(metric.inputs).map(([key, value]) => (
              <div key={key} className="contents">
                <dt className="text-ink-500">{key.replace(/_/g, " ")}</dt>
                <dd className="tabular text-ink-900">{value ?? EMPTY}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>

      {metric.notes.length > 0 && (
        <ul className="mt-4 space-y-1.5 border-t border-ink-200 pt-3 text-xs text-ink-700">
          {metric.notes.map((note, index) => (
            <li key={index} className="border-l-2 border-caution-500 pl-2">
              {note}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
