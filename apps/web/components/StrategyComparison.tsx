"use client";

import { useState } from "react";

import { ConfidenceBadge, MetBadge } from "@/components/Badges";
import { describeAssumptionPath } from "@/lib/assumptions";
import {
  EMPTY,
  formatByUnit,
  formatMoney,
  formatMonths,
  formatPercent,
  formatRatio,
  humanise,
} from "@/lib/format";
import {
  STRATEGY_LABELS,
  STRATEGY_ORDER,
  type AnalysisResponse,
  type StrategyKey,
  type StrategyResult,
} from "@atlas/shared-types";

/**
 * The five strategies side by side.
 *
 * A strategy that cannot be computed is shown as such, with the reason and the
 * missing fields — never as a column of zeros, which would read as "this
 * strategy earns nothing" rather than "we don't know yet".
 */
export function StrategyComparison({ analysis }: { analysis: AnalysisResponse }) {
  const scoreFor = (key: StrategyKey) =>
    analysis.ranking.find((entry) => entry.strategy === key)?.score ?? null;

  return (
    <div className="card overflow-hidden">
      <div className="card-header">
        <h2 className="card-title">Strategies compared</h2>
        <p className="text-xs text-ink-500">
          Ranked on profit, capital efficiency, return, cash flow, equity, time and risk —
          not on profit alone.
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="table tabular min-w-[860px]" aria-label="Strategies compared">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-white">Metric</th>
              {STRATEGY_ORDER.map((key) => {
                const result = analysis.strategies[key];
                const recommended = analysis.recommended_strategy === key;
                return (
                  <th
                    key={key}
                    className={`min-w-[150px] ${recommended ? "bg-pass-50" : ""}`}
                  >
                    <div className="flex flex-col gap-1">
                      <span className="text-sm font-semibold normal-case tracking-normal text-ink-900">
                        {STRATEGY_LABELS[key]}
                      </span>
                      {recommended && (
                        <span className="text-[10px] font-semibold uppercase text-pass-700">
                          Recommended
                        </span>
                      )}
                      {analysis.alternative_strategy === key && (
                        <span className="text-[10px] font-semibold uppercase text-ink-500">
                          Alternative
                        </span>
                      )}
                      {result?.viable && (
                        <span className="text-[11px] font-normal normal-case text-ink-500">
                          Score {formatRatio(scoreFor(key), 0)}
                        </span>
                      )}
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            <MetricRow
              label="Profit"
              analysis={analysis}
              render={(r) => formatMoney(r.profit)}
              hint="Realised profit at exit, or annual cash flow for hold strategies."
            />
            <MetricRow
              label="Cash required"
              analysis={analysis}
              render={(r) => formatMoney(r.cash_required)}
              hint="Capital committed. For BRRRR, what stays trapped after the refinance."
            />
            <MetricRow
              label="ROI"
              analysis={analysis}
              render={(r) => formatPercent(r.roi)}
              hint="Return on cash invested, not on total project cost."
            />
            <MetricRow
              label="Monthly cash flow"
              analysis={analysis}
              render={(r) => formatMoney(r.monthly_cash_flow)}
            />
            <MetricRow
              label="Equity created"
              analysis={analysis}
              render={(r) => formatMoney(r.equity_created)}
            />
            <MetricRow
              label="DSCR"
              analysis={analysis}
              render={(r) => formatRatio(r.dscr)}
              hint="Blank means no debt, so there is no coverage ratio to report."
            />
            <MetricRow
              label="Max purchase price"
              analysis={analysis}
              render={(r) => formatMoney(r.max_purchase_price)}
              hint="The most you can pay and still meet this strategy's targets."
            />
            <MetricRow
              label="Time to liquidity"
              analysis={analysis}
              render={(r) => formatMonths(r.time_to_liquidity_months)}
            />
            <MetricRow
              label="Confidence"
              analysis={analysis}
              render={(r) => <ConfidenceBadge confidence={r.confidence} label={false} />}
            />
            <MetricRow
              label="Buy box"
              analysis={analysis}
              render={(r) => <MetBadge met={r.meets_criteria} />}
            />
          </tbody>
        </table>
      </div>

      <StrategyCriteria analysis={analysis} />
    </div>
  );
}

function MetricRow({
  label,
  analysis,
  render,
  hint,
}: {
  label: string;
  analysis: AnalysisResponse;
  render: (result: StrategyResult) => React.ReactNode;
  hint?: string;
}) {
  return (
    <tr>
      <td className="sticky left-0 z-10 whitespace-nowrap bg-white font-medium text-ink-600">
        <span title={hint} className={hint ? "cursor-help border-b border-dotted border-ink-300" : ""}>
          {label}
        </span>
      </td>
      {STRATEGY_ORDER.map((key) => {
        const result = analysis.strategies[key];
        const recommended = analysis.recommended_strategy === key;
        if (!result?.viable) {
          return (
            <td key={key} className={`text-ink-400 ${recommended ? "bg-pass-50" : ""}`}>
              {EMPTY}
            </td>
          );
        }
        return (
          <td key={key} className={recommended ? "bg-pass-50" : ""}>
            {render(result)}
          </td>
        );
      })}
    </tr>
  );
}

/** Per-strategy detail: which buy-box tests passed, and why one cannot run. */
function StrategyCriteria({ analysis }: { analysis: AnalysisResponse }) {
  const [open, setOpen] = useState<StrategyKey | null>(null);

  return (
    <div className="border-t border-ink-200">
      <div className="flex flex-wrap gap-2 px-4 py-3">
        {STRATEGY_ORDER.map((key) => (
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
            {STRATEGY_LABELS[key]} detail
          </button>
        ))}
      </div>

      {open && <StrategyDetail result={analysis.strategies[open]} />}
    </div>
  );
}

function StrategyDetail({ result }: { result: StrategyResult }) {
  if (!result.viable) {
    return (
      <div className="border-t border-ink-200 bg-ink-50 px-4 py-4 text-sm">
        <p className="font-medium text-ink-800">This strategy cannot be evaluated yet.</p>
        <p className="mt-1 text-ink-600">{result.not_viable_reason}</p>
        {result.missing_inputs.length > 0 && (
          <p className="mt-2 text-ink-600">
            Missing:{" "}
            <span className="font-medium">
              {result.missing_inputs
                .map((field) => describeAssumptionPath(field) ?? humanise(field))
                .join(", ")}
            </span>
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="grid gap-5 border-t border-ink-200 bg-ink-50 px-4 py-4 md:grid-cols-3">
      <div>
        <h4 className="label mb-2">Buy box</h4>
        <ul className="space-y-1.5 text-sm">
          {result.criteria.map((criterion) => (
            <li key={criterion.name} className="flex items-baseline justify-between gap-3">
              <span className="text-ink-600">{criterion.label}</span>
              <span className="tabular whitespace-nowrap">
                <span className={criterion.met ? "text-pass-700" : "text-fail-600"}>
                  {formatByUnit(criterion.actual, criterion.unit)}
                </span>
                <span className="text-ink-400">
                  {" "}
                  / {formatByUnit(criterion.target, criterion.unit)}
                </span>
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h4 className="label mb-2">Confidence</h4>
        <ConfidenceBadge confidence={result.confidence} />
        <ul className="mt-2 space-y-1 text-xs text-ink-600">
          {result.confidence_reasons.map((reason, index) => (
            <li key={index}>{reason}</li>
          ))}
        </ul>
      </div>

      <div>
        <h4 className="label mb-2">Warnings</h4>
        {result.warnings.length === 0 ? (
          <p className="text-xs text-ink-500">None raised for this strategy.</p>
        ) : (
          <ul className="space-y-1.5 text-xs text-ink-700">
            {result.warnings.map((warning, index) => (
              <li key={index} className="border-l-2 border-caution-500 pl-2">
                {warning}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
