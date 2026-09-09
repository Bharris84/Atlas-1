"use client";

import { useEffect, useState } from "react";

import {
  AiPanel,
  MissingInfoPanel,
  RationalePanel,
  RiskPanel,
  ScorePanel,
} from "@/components/AnalysisPanels";
import { CapitalEfficiencyPanel } from "@/components/CapitalEfficiencyPanel";
import {
  AssumptionsPanel,
  DealInputsPanel,
  EvidencePanel,
  RiskFlagPanel,
} from "@/components/DealInputs";
import { ErrorState } from "@/components/States";
import { StrategyComparison } from "@/components/StrategyComparison";
import type { UseAnalysisResult } from "@/hooks/useAnalysis";
import { api } from "@/lib/api";

/**
 * The shared analysis surface: inputs on the left, results on the right.
 *
 * Used by both the standalone analyzer and a property's Financials tab, so the
 * two cannot drift apart.
 */
export function AnalysisWorkspace({
  state,
  header,
}: {
  state: UseAnalysisResult;
  header?: React.ReactNode;
}) {
  const { analysis, loading, error } = state;
  const [defaults, setDefaults] = useState<Record<string, any> | null>(null);

  useEffect(() => {
    // The user's saved buy box, so untouched fields show what will actually
    // be used rather than an empty box.
    api
      .getSettings()
      .then((settings) => setDefaults(settings.default_assumptions))
      .catch(() => setDefaults(null));
  }, []);

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(340px,420px)_1fr]">
      <div className="space-y-4">
        {header}
        <DealInputsPanel state={state} />
        <EvidencePanel state={state} />
        <RiskFlagPanel state={state} />
        <AssumptionsPanel state={state} defaults={defaults} />
      </div>

      {/* min-w-0: a grid item defaults to min-width:auto, so the wide strategy
          table would stretch this column and scroll the whole page sideways
          instead of scrolling inside its own container. */}
      <div className="min-w-0 space-y-4">
        {error && <ErrorState message={error} onRetry={state.refresh} />}

        {!analysis && !error && (
          <div className="card px-4 py-10 text-center text-sm text-ink-500">
            {loading
              ? "Running the analysis…"
              : "Enter a purchase price, ARV, rehab or rent to begin."}
          </div>
        )}

        {analysis && (
          <>
            <div
              className={`transition-opacity ${loading ? "opacity-60" : "opacity-100"}`}
            >
              <StrategyComparison analysis={analysis} />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <ScorePanel scoring={analysis.scoring} />
              <div className="space-y-4">
                <RationalePanel analysis={analysis} />
                <MissingInfoPanel analysis={analysis} />
              </div>
            </div>
            <CapitalEfficiencyPanel analysis={analysis} />
            <RiskPanel scoring={analysis.scoring} />
            <AiPanel analysis={analysis} />
            <p className="text-center text-[11px] text-ink-400">
              Calculated by the Atlas financial engine v{analysis.engine_version}. Every
              figure is reproducible from the assumptions shown.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
