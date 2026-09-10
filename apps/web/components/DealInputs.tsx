"use client";

import { ProvisionalTag, UnknownTag } from "@/components/Badges";
import {
  ASSUMPTION_GROUPS,
  toDisplayValue,
  unitSuffix,
  type AssumptionField,
} from "@/lib/assumptions";
import type { UseAnalysisResult } from "@/hooks/useAnalysis";
import type { RehabBasis, RentBasis, ValueBasis } from "@atlas/shared-types";

const ARV_BASIS: { value: ValueBasis; label: string }[] = [
  { value: "unknown", label: "Not recorded" },
  { value: "comparable_sales", label: "Comparable sales" },
  { value: "appraisal", label: "Appraisal" },
  { value: "broker_opinion", label: "Broker price opinion" },
  { value: "automated_valuation", label: "Automated valuation" },
  { value: "list_price", label: "List price" },
  { value: "user_entered", label: "Entered manually" },
];

const REHAB_BASIS: { value: RehabBasis; label: string }[] = [
  { value: "unknown", label: "Not recorded" },
  { value: "contractor_bid", label: "Contractor bid" },
  { value: "detailed_scope", label: "Line-item scope" },
  { value: "walkthrough", label: "Walkthrough" },
  { value: "per_sqft_estimate", label: "Per square foot" },
  { value: "user_entered", label: "Entered manually" },
];

const RENT_BASIS: { value: RentBasis; label: string }[] = [
  { value: "unknown", label: "Not recorded" },
  { value: "lease_in_place", label: "Lease in place" },
  { value: "rent_roll", label: "Rent roll" },
  { value: "rental_comps", label: "Rental comps" },
  { value: "automated_estimate", label: "Automated estimate" },
  { value: "user_entered", label: "Entered manually" },
];

const DECLARABLE_RISKS = [
  { code: "title_issue_suspected", label: "Possible title defect" },
  { code: "structural_concern", label: "Structural uncertainty" },
  { code: "environmental_concern", label: "Environmental concern" },
  { code: "financing_uncertainty", label: "Financing not committed" },
  { code: "occupied_property", label: "Property occupied" },
  { code: "permit_or_code_issue", label: "Permit or code issue" },
  { code: "hoa_restrictions", label: "HOA restrictions" },
  { code: "flood_zone", label: "Flood zone" },
];

export function DealInputsPanel({ state }: { state: UseAnalysisResult }) {
  const { draft, setField } = state;

  return (
    <div className="card">
      <div className="card-header">
        <h2 className="card-title">Deal inputs</h2>
        <span className="text-xs text-ink-500">Results update as you type</span>
      </div>
      <div className="grid gap-3 px-4 py-4 sm:grid-cols-2">
        <MoneyInput
          label="Purchase price"
          value={draft.purchase_price}
          onChange={(v) => setField("purchase_price", v)}
        />
        <MoneyInput
          label="After-repair value (ARV)"
          value={draft.arv}
          onChange={(v) => setField("arv", v)}
        />
        <MoneyInput
          label="Rehab"
          value={draft.rehab}
          onChange={(v) => setField("rehab", v)}
        />
        <MoneyInput
          label="Monthly rent"
          value={draft.monthly_rent}
          onChange={(v) => setField("monthly_rent", v)}
        />
        <MoneyInput
          label="ARV low"
          hint="Optional. A wide range costs a confidence level."
          value={draft.arv_low}
          onChange={(v) => setField("arv_low", v)}
        />
        <MoneyInput
          label="ARV high"
          value={draft.arv_high}
          onChange={(v) => setField("arv_high", v)}
        />
        <MoneyInput
          label="Rehab low"
          value={draft.rehab_low}
          onChange={(v) => setField("rehab_low", v)}
        />
        <MoneyInput
          label="Rehab high"
          value={draft.rehab_high}
          onChange={(v) => setField("rehab_high", v)}
        />
      </div>
    </div>
  );
}

/**
 * Where the numbers came from. This drives the confidence rating, and is the
 * difference between "ARV is $250,000" and "someone typed $250,000".
 */
export function EvidencePanel({ state }: { state: UseAnalysisResult }) {
  const { draft, setEvidence } = state;
  const evidence = draft.evidence;

  return (
    <div className="card">
      <div className="card-header">
        <h2 className="card-title">Evidence</h2>
        <span className="text-xs text-ink-500">Determines confidence</span>
      </div>
      <div className="grid gap-3 px-4 py-4 sm:grid-cols-2">
        <Select
          label="ARV based on"
          value={evidence.arv_basis ?? "unknown"}
          options={ARV_BASIS}
          onChange={(value) => setEvidence({ arv_basis: value as ValueBasis })}
        />
        <Select
          label="Rehab based on"
          value={evidence.rehab_basis ?? "unknown"}
          options={REHAB_BASIS}
          onChange={(value) => setEvidence({ rehab_basis: value as RehabBasis })}
        />
        <Select
          label="Rent based on"
          value={evidence.rent_basis ?? "unknown"}
          options={RENT_BASIS}
          onChange={(value) => setEvidence({ rent_basis: value as RentBasis })}
        />
        <NumberInput
          label="Comparable sales on file"
          value={evidence.comp_count?.toString() ?? ""}
          onChange={(value) =>
            setEvidence({ comp_count: value === "" ? 0 : Number(value) })
          }
        />
        <NumberInput
          label="Average comp similarity (0–1)"
          value={evidence.average_comp_similarity ?? ""}
          onChange={(value) =>
            setEvidence({ average_comp_similarity: value === "" ? null : value })
          }
        />
        <NumberInput
          label="Average comp age (days)"
          value={evidence.average_comp_age_days?.toString() ?? ""}
          onChange={(value) =>
            setEvidence({
              average_comp_age_days: value === "" ? null : Number(value),
            })
          }
        />
        <div className="sm:col-span-2 flex flex-wrap gap-4 pt-1">
          <Checkbox
            label="Property walked"
            checked={Boolean(evidence.property_visited)}
            onChange={(checked) => setEvidence({ property_visited: checked })}
          />
          <Checkbox
            label="Inspection completed"
            checked={Boolean(evidence.inspection_completed)}
            onChange={(checked) => setEvidence({ inspection_completed: checked })}
          />
          <Checkbox
            label="Title reviewed"
            checked={Boolean(evidence.title_reviewed)}
            onChange={(checked) => setEvidence({ title_reviewed: checked })}
          />
        </div>
      </div>
    </div>
  );
}

export function RiskFlagPanel({ state }: { state: UseAnalysisResult }) {
  const { draft, toggleRiskFlag } = state;
  return (
    <div className="card">
      <div className="card-header">
        <h2 className="card-title">Declared risks</h2>
        <span className="text-xs text-ink-500">Some force human review</span>
      </div>
      <div className="grid gap-2 px-4 py-4 sm:grid-cols-2">
        {DECLARABLE_RISKS.map((risk) => (
          <Checkbox
            key={risk.code}
            label={risk.label}
            checked={draft.risk_flags.includes(risk.code)}
            onChange={() => toggleRiskFlag(risk.code)}
          />
        ))}
      </div>
    </div>
  );
}

/**
 * Every assumption behind the result, grouped and editable.
 *
 * An untouched field shows the engine's provisional default and is tagged as
 * such. Clearing an edited field returns it to that default rather than
 * sending an empty override.
 *
 * Operating expenses are the exception: they have no default, so a blank one
 * is unknown rather than defaulted, and clearing it is a real answer ("I don't
 * know"). Those fields are tagged and coloured differently, because an empty
 * box tagged "default" would tell the user Atlas had picked a number when it
 * had picked nothing and left the expense out of the arithmetic.
 */
export function AssumptionsPanel({
  state,
  defaults,
}: {
  state: UseAnalysisResult;
  defaults: Record<string, any> | null;
}) {
  const { setAssumption, resetAssumption, isOverridden, draft } = state;

  const currentValue = (field: AssumptionField): string => {
    const overridden = readPath(draft.assumptions, field.path);
    if (overridden !== undefined) return toDisplayValue(overridden, field.kind);
    return toDisplayValue(readPath(defaults, field.path), field.kind);
  };

  return (
    <div className="card">
      <div className="card-header">
        <h2 className="card-title">Assumptions</h2>
        <span className="text-xs text-ink-500">
          Every number driving the result. Clear a field to restore its default.
        </span>
      </div>

      <div className="divide-y divide-ink-200">
        {ASSUMPTION_GROUPS.map((group) => (
          <details key={group.key} className="group" open={group.key === "flip"}>
            <summary className="flex cursor-pointer items-center justify-between px-4 py-3 hover:bg-ink-50">
              <div>
                <span className="text-sm font-medium text-ink-900">{group.title}</span>
                <p className="mt-0.5 max-w-xl text-xs text-ink-500">{group.description}</p>
              </div>
              <span className="text-xs text-ink-400 group-open:hidden">Show</span>
              <span className="hidden text-xs text-ink-400 group-open:inline">Hide</span>
            </summary>

            <div className="grid gap-3 px-4 pb-4 sm:grid-cols-2 lg:grid-cols-3">
              {group.fields.map((field) => {
                const overridden = isOverridden(field.path);
                const value = currentValue(field);
                // Three states, not two. Blank on an expense field means
                // nobody has established it — which is why it gets its own
                // tag rather than the "default" one: there is no default.
                const unknown = field.unknownable === true && value === "";
                return (
                  <div key={field.path}>
                    <label className="label flex items-center gap-1">
                      <span title={field.help} className={field.help ? "cursor-help" : ""}>
                        {field.label}
                      </span>
                      {unknown && <UnknownTag />}
                      {!unknown && !overridden && <ProvisionalTag />}
                      {overridden && (
                        <button
                          type="button"
                          onClick={() => resetAssumption(field.path)}
                          className="ml-auto text-[10px] font-medium normal-case text-ink-500 underline hover:text-ink-800"
                        >
                          reset
                        </button>
                      )}
                    </label>
                    <div className="relative mt-1">
                      <input
                        className={`input tabular pr-8 ${
                          unknown
                            ? "border-caution-500/50 bg-caution-50"
                            : overridden
                              ? "border-ink-500 bg-ink-50"
                              : ""
                        }`}
                        inputMode="decimal"
                        value={value}
                        placeholder={unknown ? "not known" : undefined}
                        onChange={(event) =>
                          setAssumption(field.path, event.target.value, field.kind)
                        }
                        aria-label={field.label}
                      />
                      <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-ink-400">
                        {unitSuffix(field.kind)}
                      </span>
                    </div>
                    {unknown && (
                      <p className="mt-1 text-[11px] leading-snug text-caution-700">
                        Omitted from the result. Enter 0 if it does not apply.
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </details>
        ))}
      </div>
    </div>
  );
}

function readPath(source: Record<string, any> | null | undefined, path: string): any {
  if (!source) return undefined;
  return path.split(".").reduce<any>((node, key) => {
    if (node === null || node === undefined || typeof node !== "object") return undefined;
    return node[key];
  }, source);
}

// --- Primitives -------------------------------------------------------------

export function MoneyInput({
  label,
  value,
  onChange,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
}) {
  return (
    <div>
      <label className="label" htmlFor={`field-${label}`}>
        {label}
      </label>
      <div className="relative mt-1">
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-ink-400">
          $
        </span>
        <input
          id={`field-${label}`}
          className="input tabular pl-6"
          inputMode="decimal"
          placeholder="—"
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      </div>
      {hint && <p className="mt-1 text-[11px] text-ink-500">{hint}</p>}
    </div>
  );
}

function NumberInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label className="label" htmlFor={`num-${label}`}>
        {label}
      </label>
      <input
        id={`num-${label}`}
        className="input tabular mt-1"
        inputMode="decimal"
        placeholder="—"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

function Select<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: T; label: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label className="label" htmlFor={`select-${label}`}>
        {label}
      </label>
      <select
        id={`select-${label}`}
        className="input mt-1"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function Checkbox({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-ink-700">
      <input
        type="checkbox"
        className="h-4 w-4 rounded border-ink-300 text-ink-900 focus:ring-ink-500"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      {label}
    </label>
  );
}
