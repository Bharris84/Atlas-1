"use client";

import { useState } from "react";

import {
  AssertionBadge,
  ConfidenceBadge,
  SeverityBadge,
  VerdictBadge,
} from "@/components/Badges";
import { describeAssumptionPath } from "@/lib/assumptions";
import { EMPTY, formatPercent, formatScore, humanise } from "@/lib/format";
import {
  STRATEGY_LABELS,
  type AgentOutput,
  type AnalysisResponse,
  type DealScore,
} from "@atlas/shared-types";

/**
 * The verdict, the score, and — importantly — how much of the scoring rubric
 * could actually be assessed. A high score on a third of the rubric is not the
 * same claim as a high score on all of it, and the UI must not let those look
 * alike.
 */
export function ScorePanel({ scoring }: { scoring: DealScore }) {
  const assessed = scoring.components.filter((c) => c.assessed);
  const unassessed = scoring.components.filter((c) => !c.assessed);

  return (
    <div className="card">
      <div className="card-header">
        <h2 className="card-title">Deal score</h2>
        <VerdictBadge verdict={scoring.verdict} />
      </div>

      <div className="flex items-start gap-5 px-4 py-4">
        <div className="text-center">
          <div className="tabular text-4xl font-semibold text-ink-900">
            {formatScore(scoring.score)}
          </div>
          <div className="text-[11px] uppercase tracking-wide text-ink-500">out of 100</div>
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm text-ink-700">{scoring.verdict_reason}</p>
          <p className="mt-2 text-xs text-ink-500">
            Assessed on {formatPercent(scoring.coverage, 0)} of the rubric.{" "}
            {unassessed.length > 0 && (
              <>
                {unassessed.map((c) => c.label).join(" and ")}{" "}
                {unassessed.length === 1 ? "is" : "are"} excluded rather than guessed.
              </>
            )}
          </p>
        </div>
      </div>

      <div className="border-t border-ink-200 px-4 py-3">
        <ul className="space-y-2">
          {assessed.map((component) => (
            <li key={component.name}>
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className="text-ink-700">{component.label}</span>
                <span className="tabular text-ink-900">
                  {formatScore(component.score)}
                  <span className="text-xs text-ink-400">
                    {" "}
                    &times; {formatPercent(component.weight, 0)}
                  </span>
                </span>
              </div>
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded bg-ink-100">
                <div
                  className="h-full rounded bg-ink-500"
                  style={{ width: `${Math.min(Number(component.score ?? 0), 100)}%` }}
                />
              </div>
              <p className="mt-1 text-[11px] text-ink-500">{component.reason}</p>
            </li>
          ))}
        </ul>

        {unassessed.length > 0 && (
          <ul className="mt-3 space-y-2 border-t border-dashed border-ink-200 pt-3">
            {unassessed.map((component) => (
              <li key={component.name} className="text-sm">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-ink-500">{component.label}</span>
                  <span className="text-xs text-ink-400">
                    not assessed &middot; {formatPercent(component.weight, 0)} of rubric
                  </span>
                </div>
                <p className="mt-0.5 text-[11px] text-ink-500">{component.reason}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/** Risk flags, most severe first. A blocking flag overrides the score. */
export function RiskPanel({ scoring }: { scoring: DealScore }) {
  return (
    <div className="card">
      <div className="card-header">
        <h2 className="card-title">Risks</h2>
        <span className="text-xs text-ink-500">
          Risk score {formatScore(scoring.risk_score)} / 100
        </span>
      </div>

      {scoring.requires_human_review && (
        <div className="border-b border-fail-100 bg-fail-50 px-4 py-3 text-sm text-fail-700">
          <p className="font-semibold">This deal requires human review.</p>
          <p className="mt-1">
            A blocking risk flag overrides the numeric score. The score is still shown
            above, but it does not clear this.
          </p>
        </div>
      )}

      {scoring.risk_flags.length === 0 ? (
        <p className="px-4 py-4 text-sm text-ink-500">No risk flags raised.</p>
      ) : (
        <ul className="divide-y divide-ink-100">
          {scoring.risk_flags.map((flag) => (
            <li key={flag.code} className="px-4 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <SeverityBadge severity={flag.severity} />
                <span className="text-sm font-medium text-ink-900">{flag.label}</span>
                {flag.blocks_pursue && (
                  <span className="text-[11px] font-medium uppercase text-fail-600">
                    blocking
                  </span>
                )}
                <span className="ml-auto text-[11px] text-ink-400">{flag.source}</span>
              </div>
              <p className="mt-1 text-sm text-ink-600">{flag.detail}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** What Atlas does not know. Shown as prominently as what it does. */
export function MissingInfoPanel({ analysis }: { analysis: AnalysisResponse }) {
  const missing = analysis.missing_information;
  return (
    <div className="card">
      <div className="card-header">
        <h2 className="card-title">Missing information</h2>
        <ConfidenceBadge confidence={analysis.overall_confidence} />
      </div>
      <div className="px-4 py-4">
        {missing.length === 0 ? (
          <p className="text-sm text-ink-500">
            Every input the engine needs has been supplied.
          </p>
        ) : (
          <>
            <p className="mb-2 text-sm text-ink-600">
              These are absent, not zero. Expenses listed here were left out of the
              arithmetic rather than guessed, so the figures above read better than
              the property does. Enter 0 where one genuinely does not apply.
            </p>
            <ul className="flex flex-wrap gap-2">
              {missing.map((field) => (
                <li
                  key={field}
                  className="rounded border border-caution-500/40 bg-caution-50 px-2 py-1 text-xs font-medium text-caution-700"
                >
                  {describeAssumptionPath(field) ?? humanise(field)}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}

/** The engine's own explanation of the ranking. Arithmetic, not prose. */
export function RationalePanel({ analysis }: { analysis: AnalysisResponse }) {
  return (
    <div className="card">
      <div className="card-header">
        <h2 className="card-title">Why this ranking</h2>
        <span className="text-xs text-ink-500">
          {analysis.viable_exit_count} exit
          {analysis.viable_exit_count === 1 ? "" : "s"} clear the buy box
        </span>
      </div>
      <ul className="space-y-2 px-4 py-4 text-sm text-ink-700">
        {analysis.rationale.map((line, index) => (
          <li key={index} className="flex gap-2">
            <span className="text-ink-300">&bull;</span>
            <span>{line}</span>
          </li>
        ))}
      </ul>
      {analysis.recommended_strategy && (
        <div className="border-t border-ink-200 bg-ink-50 px-4 py-3 text-sm">
          <span className="text-ink-500">Recommended: </span>
          <span className="font-semibold text-ink-900">
            {STRATEGY_LABELS[analysis.recommended_strategy]}
          </span>
          {analysis.alternative_strategy && (
            <>
              <span className="text-ink-500"> &middot; Alternative: </span>
              <span className="font-medium text-ink-800">
                {STRATEGY_LABELS[analysis.alternative_strategy]}
              </span>
            </>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * AI output, kept visibly separate from the computed numbers.
 *
 * The disclaimer is not decoration: a reader must always be able to tell which
 * parts of the screen were calculated and which were written by a model.
 */
export function AiPanel({ analysis }: { analysis: AnalysisResponse }) {
  const ai = analysis.ai_analysis;
  const [tab, setTab] = useState<"research" | "underwriting" | "strategist">(
    "underwriting"
  );

  if (!ai) {
    return (
      <div className="card">
        <div className="card-header">
          <h2 className="card-title">AI analysis</h2>
        </div>
        <p className="px-4 py-4 text-sm text-ink-500">
          Not generated for this analysis. The numbers above do not depend on it.
        </p>
      </div>
    );
  }

  const active = ai[tab];

  return (
    <div className="card">
      <div className="card-header">
        <h2 className="card-title">AI analysis</h2>
        <span className="text-xs text-ink-500">
          {active.deterministic
            ? "Composed deterministically from the engine's numbers"
            : `Generated by ${active.provider}${active.model ? ` (${active.model})` : ""}`}
        </span>
      </div>

      <div className="flex gap-1 border-b border-ink-200 px-4 py-2">
        {(["research", "underwriting", "strategist"] as const).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`rounded px-2.5 py-1 text-xs font-medium capitalize transition ${
              tab === key
                ? "bg-ink-900 text-white"
                : "text-ink-600 hover:bg-ink-100"
            }`}
          >
            {key}
          </button>
        ))}
      </div>

      <div className="space-y-4 px-4 py-4">
        <p className="text-sm font-medium text-ink-900">{active.summary}</p>

        {active.claims.length > 0 && (
          <div>
            <h4 className="label mb-2">What is known</h4>
            <ul className="space-y-1.5">
              {active.claims.map((claim, index) => (
                <li key={index} className="flex flex-wrap items-baseline gap-2 text-sm">
                  <AssertionBadge assertion={claim.assertion} />
                  <span className="text-ink-600">{claim.label}:</span>
                  <span className="tabular font-medium text-ink-900">
                    {claim.value ?? EMPTY}
                  </span>
                  {claim.source && (
                    <span className="text-[11px] text-ink-400">({claim.source})</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        <AgentList title="Analysis" items={active.narrative} />
        <AgentList title="Challenges to the assumptions" items={active.challenges} />
        <AgentList title="Risks" items={active.risks} />
        <AgentList title="Diligence to do next" items={active.questions} />
        <AgentList title="Missing information" items={active.missing_information} />

        {active.sources.length > 0 && (
          <div>
            <h4 className="label mb-1">Sources</h4>
            <p className="text-xs text-ink-500">{active.sources.join(" &middot; ")}</p>
          </div>
        )}

        <p className="border-t border-ink-200 pt-3 text-[11px] leading-relaxed text-ink-500">
          {active.disclaimer}
        </p>
      </div>
    </div>
  );
}

function AgentList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h4 className="label mb-1.5">{title}</h4>
      <ul className="space-y-1.5 text-sm text-ink-700">
        {items.map((item, index) => (
          <li key={index} className="flex gap-2">
            <span className="text-ink-300">&bull;</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
