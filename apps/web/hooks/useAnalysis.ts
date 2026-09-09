"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { deletePath, setPath, toApiValue, type FieldKind } from "@/lib/assumptions";
import type { AnalysisRequest, AnalysisResponse, Evidence } from "@atlas/shared-types";

/**
 * The draft a user is editing.
 *
 * `assumptions` holds ONLY the fields that have been explicitly overridden.
 * Anything untouched is absent, so the engine's provisional default applies and
 * the UI can honestly mark it as a default rather than as the user's choice.
 */
export interface Draft {
  purchase_price: string;
  arv: string;
  arv_low: string;
  arv_high: string;
  rehab: string;
  rehab_low: string;
  rehab_high: string;
  monthly_rent: string;
  evidence: Partial<Evidence>;
  assumptions: Record<string, any>;
  risk_flags: string[];
}

export const EMPTY_DRAFT: Draft = {
  purchase_price: "",
  arv: "",
  arv_low: "",
  arv_high: "",
  rehab: "",
  rehab_low: "",
  rehab_high: "",
  monthly_rent: "",
  evidence: {},
  assumptions: {},
  risk_flags: [],
};

const MONEY_FIELDS = [
  "purchase_price",
  "arv",
  "arv_low",
  "arv_high",
  "rehab",
  "rehab_low",
  "rehab_high",
  "monthly_rent",
] as const;

/** Strip formatting a user might paste in ("$150,000"). */
function cleanMoney(raw: string): string | null {
  const trimmed = raw.trim().replace(/[$,\s]/g, "");
  if (trimmed === "") return null;
  return Number.isFinite(Number(trimmed)) ? trimmed : null;
}

export function draftToRequest(draft: Draft, includeAi = false): AnalysisRequest {
  const request: AnalysisRequest = { include_ai: includeAi };
  for (const field of MONEY_FIELDS) {
    const value = cleanMoney(draft[field]);
    if (value !== null) (request as Record<string, unknown>)[field] = value;
  }
  if (Object.keys(draft.evidence).length > 0) request.evidence = draft.evidence;
  if (Object.keys(draft.assumptions).length > 0) request.assumptions = draft.assumptions;
  if (draft.risk_flags.length > 0) request.risk_flags = draft.risk_flags;
  return request;
}

/** True when there is enough entered for an analysis to say anything at all. */
export function draftHasInput(draft: Draft): boolean {
  return MONEY_FIELDS.some((field) => cleanMoney(draft[field]) !== null);
}

export interface UseAnalysisResult {
  draft: Draft;
  analysis: AnalysisResponse | null;
  loading: boolean;
  error: string | null;
  setField: (field: keyof Draft, value: string) => void;
  setAssumption: (path: string, raw: string, kind: FieldKind) => void;
  resetAssumption: (path: string) => void;
  setEvidence: (patch: Partial<Evidence>) => void;
  toggleRiskFlag: (code: string) => void;
  setDraft: (draft: Draft) => void;
  isOverridden: (path: string) => boolean;
  refresh: () => void;
}

/**
 * Recompute as the user types.
 *
 * Debounced so a keystroke does not fire a request per character, and
 * sequenced so a slow earlier response cannot overwrite a newer one — without
 * that, typing quickly can leave the screen showing stale numbers, which for
 * an underwriting tool is worse than showing nothing.
 */
export function useAnalysis(
  initial: Draft = EMPTY_DRAFT,
  debounceMs = 300
): UseAnalysisResult {
  const [draft, setDraft] = useState<Draft>(initial);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const requestSequence = useRef(0);
  const request = useMemo(() => draftToRequest(draft), [draft]);
  const hasInput = draftHasInput(draft);

  useEffect(() => {
    if (!hasInput) {
      setAnalysis(null);
      setError(null);
      setLoading(false);
      return;
    }

    const sequence = ++requestSequence.current;
    setLoading(true);
    const timer = setTimeout(() => {
      api
        .analyze(request)
        .then((result) => {
          // Ignore a response that a newer request has already superseded.
          if (sequence !== requestSequence.current) return;
          setAnalysis(result);
          setError(null);
        })
        .catch((cause) => {
          if (sequence !== requestSequence.current) return;
          setError(
            cause instanceof ApiError ? cause.message : "Could not run the analysis."
          );
        })
        .finally(() => {
          if (sequence === requestSequence.current) setLoading(false);
        });
    }, debounceMs);

    return () => clearTimeout(timer);
  }, [request, hasInput, debounceMs, nonce]);

  const setField = useCallback((field: keyof Draft, value: string) => {
    setDraft((current) => ({ ...current, [field]: value }));
  }, []);

  const setAssumption = useCallback((path: string, raw: string, kind: FieldKind) => {
    setDraft((current) => {
      const value = toApiValue(raw, kind);
      // Clearing a field returns it to the engine default rather than sending
      // an empty override.
      const assumptions =
        value === null
          ? deletePath(current.assumptions, path)
          : setPath(current.assumptions, path, value);
      return { ...current, assumptions };
    });
  }, []);

  const resetAssumption = useCallback((path: string) => {
    setDraft((current) => ({
      ...current,
      assumptions: deletePath(current.assumptions, path),
    }));
  }, []);

  const setEvidence = useCallback((patch: Partial<Evidence>) => {
    setDraft((current) => ({
      ...current,
      evidence: { ...current.evidence, ...patch },
    }));
  }, []);

  const toggleRiskFlag = useCallback((code: string) => {
    setDraft((current) => ({
      ...current,
      risk_flags: current.risk_flags.includes(code)
        ? current.risk_flags.filter((flag) => flag !== code)
        : [...current.risk_flags, code],
    }));
  }, []);

  const isOverridden = useCallback(
    (path: string) => {
      let node: any = draft.assumptions;
      for (const key of path.split(".")) {
        if (node === null || node === undefined || typeof node !== "object") return false;
        node = node[key];
      }
      return node !== undefined;
    },
    [draft.assumptions]
  );

  return {
    draft,
    analysis,
    loading,
    error,
    setField,
    setAssumption,
    resetAssumption,
    setEvidence,
    toggleRiskFlag,
    setDraft,
    isOverridden,
    refresh: () => setNonce((n) => n + 1),
  };
}
