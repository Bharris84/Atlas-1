import type {
  Assertion,
  Confidence,
  RiskSeverity,
  Verdict,
} from "@atlas/shared-types";

const BASE =
  "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide";

export function VerdictBadge({ verdict }: { verdict: Verdict | null | undefined }) {
  if (!verdict) {
    return <span className={`${BASE} bg-ink-100 text-ink-500`}>Not analyzed</span>;
  }
  const styles: Record<Verdict, string> = {
    PURSUE: "bg-pass-100 text-pass-700",
    INVESTIGATE: "bg-caution-100 text-caution-700",
    PASS: "bg-ink-200 text-ink-700",
    HUMAN_REVIEW_REQUIRED: "bg-fail-100 text-fail-700",
  };
  const labels: Record<Verdict, string> = {
    PURSUE: "Pursue",
    INVESTIGATE: "Investigate",
    PASS: "Pass",
    HUMAN_REVIEW_REQUIRED: "Human review",
  };
  return <span className={`${BASE} ${styles[verdict]}`}>{labels[verdict]}</span>;
}

/**
 * Confidence is shown next to every headline estimate. A number with weak
 * support must never look like a number with strong support.
 */
export function ConfidenceBadge({
  confidence,
  label = true,
}: {
  confidence: Confidence | null | undefined;
  label?: boolean;
}) {
  if (!confidence) return null;
  const styles: Record<Confidence, string> = {
    HIGH: "bg-pass-100 text-pass-700",
    MEDIUM: "bg-caution-100 text-caution-700",
    LOW: "bg-fail-100 text-fail-700",
  };
  return (
    <span className={`${BASE} ${styles[confidence]}`}>
      {label ? `${confidence} confidence` : confidence}
    </span>
  );
}

/** FACT / ESTIMATE / INFERENCE / UNKNOWN. The label is the whole point. */
export function AssertionBadge({ assertion }: { assertion: Assertion }) {
  const styles: Record<Assertion, string> = {
    FACT: "bg-pass-100 text-pass-700",
    ESTIMATE: "bg-caution-100 text-caution-700",
    INFERENCE: "bg-ink-200 text-ink-700",
    UNKNOWN: "bg-fail-100 text-fail-700",
  };
  return <span className={`${BASE} ${styles[assertion]}`}>{assertion}</span>;
}

export function SeverityBadge({ severity }: { severity: RiskSeverity }) {
  const styles: Record<RiskSeverity, string> = {
    CRITICAL: "bg-fail-100 text-fail-700",
    WARNING: "bg-caution-100 text-caution-700",
    INFO: "bg-ink-200 text-ink-700",
  };
  return <span className={`${BASE} ${styles[severity]}`}>{severity}</span>;
}

export function MetBadge({ met }: { met: boolean }) {
  return (
    <span className={`${BASE} ${met ? "bg-pass-100 text-pass-700" : "bg-ink-200 text-ink-600"}`}>
      {met ? "Met" : "Not met"}
    </span>
  );
}

export function StatusPill({ status }: { status: string }) {
  return (
    <span className="inline-flex rounded-full bg-ink-100 px-2 py-0.5 text-[11px] font-medium text-ink-600">
      {status.replace(/_/g, " ")}
    </span>
  );
}

/**
 * Marks a value that came from Atlas's provisional defaults rather than from
 * anything specific to this property.
 */
export function ProvisionalTag() {
  return (
    <span
      className="ml-1 cursor-help rounded bg-ink-100 px-1 text-[10px] font-medium text-ink-500"
      title="Provisional default. Not a market-verified figure for this property."
    >
      default
    </span>
  );
}
