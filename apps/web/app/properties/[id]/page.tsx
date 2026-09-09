"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  AiPanel,
  MissingInfoPanel,
  RationalePanel,
  RiskPanel,
  ScorePanel,
} from "@/components/AnalysisPanels";
import { AnalysisWorkspace } from "@/components/AnalysisWorkspace";
import { ConfidenceBadge, StatusPill, VerdictBadge } from "@/components/Badges";
import { PageHeader } from "@/components/Shell";
import { EmptyState, ErrorState, LoadingState, PlannedFeature } from "@/components/States";
import { StrategyComparison } from "@/components/StrategyComparison";
import { EMPTY_DRAFT, draftToRequest, useAnalysis, type Draft } from "@/hooks/useAnalysis";
import { api } from "@/lib/api";
import {
  EMPTY,
  formatDate,
  formatDateTime,
  formatMoney,
  formatNumber,
  formatPercent,
  humanise,
} from "@/lib/format";
import type {
  AnalysisResponse,
  AnalysisSummary,
  AssumptionAudit,
  Comp,
  Communication,
  Owner,
  Property,
} from "@atlas/shared-types";

const TABS = [
  "Overview",
  "Owner",
  "Market",
  "Listing",
  "Comps",
  "Financials",
  "Strategies",
  "Risks",
  "Communications",
  "Documents",
  "AI Analysis",
] as const;

type Tab = (typeof TABS)[number];

export default function PropertyPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const propertyId = params.id;

  const [property, setProperty] = useState<Property | null>(null);
  const [analyses, setAnalyses] = useState<AnalysisSummary[]>([]);
  const [current, setCurrent] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("Overview");

  const load = useCallback(() => {
    setError(null);
    Promise.all([api.getProperty(propertyId), api.listAnalyses(propertyId)])
      .then(async ([propertyRow, analysisRows]) => {
        setProperty(propertyRow);
        setAnalyses(analysisRows);
        if (analysisRows.length > 0) {
          setCurrent(await api.getAnalysis(analysisRows[0].id));
        }
      })
      .catch((cause) =>
        setError(cause instanceof Error ? cause.message : "Could not load the property.")
      );
  }, [propertyId]);

  useEffect(load, [load]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!property) return <LoadingState label="Loading property…" />;

  return (
    <>
      <PageHeader
        title={property.address}
        description={
          [property.city, property.state, property.zip_code].filter(Boolean).join(", ") ||
          undefined
        }
        actions={
          <>
            <StatusPill status={property.property_status} />
            {current && <VerdictBadge verdict={current.scoring.verdict} />}
          </>
        }
      />

      <div className="mb-4 flex flex-wrap gap-1 border-b border-ink-200">
        {TABS.map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setTab(name)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm transition ${
              tab === name
                ? "border-ink-900 font-medium text-ink-900"
                : "border-transparent text-ink-500 hover:text-ink-800"
            }`}
          >
            {name}
          </button>
        ))}
      </div>

      {tab === "Overview" && (
        <OverviewTab property={property} analyses={analyses} current={current} />
      )}
      {tab === "Owner" && <OwnerTab propertyId={propertyId} />}
      {tab === "Market" && (
        <PlannedFeature
          title="Market intelligence is not built yet"
          description="Atlas does not yet hold market data for this property, and the deal score reflects that: the Market category is excluded from the rubric rather than filled with a guess."
          planned={[
            "Median sale price, rent and days-on-market by ZIP",
            "Rent-to-price trends over time",
            "Absorption and inventory signals",
          ]}
        />
      )}
      {tab === "Listing" && <ListingTab property={property} />}
      {tab === "Comps" && <CompsTab propertyId={propertyId} />}
      {tab === "Financials" && (
        <FinancialsTab
          property={property}
          current={current}
          onSaved={(analysis) => {
            setCurrent(analysis);
            api.listAnalyses(propertyId).then(setAnalyses);
          }}
        />
      )}
      {tab === "Strategies" &&
        (current ? (
          <div className="space-y-4">
            <StrategyComparison analysis={current} />
            <div className="grid gap-4 lg:grid-cols-2">
              <RationalePanel analysis={current} />
              <MissingInfoPanel analysis={current} />
            </div>
          </div>
        ) : (
          <NoAnalysis onGo={() => setTab("Financials")} />
        ))}
      {tab === "Risks" &&
        (current ? (
          <div className="grid gap-4 lg:grid-cols-2">
            <RiskPanel scoring={current.scoring} />
            <ScorePanel scoring={current.scoring} />
          </div>
        ) : (
          <NoAnalysis onGo={() => setTab("Financials")} />
        ))}
      {tab === "Communications" && <CommunicationsTab propertyId={propertyId} />}
      {tab === "Documents" && (
        <PlannedFeature
          title="Document storage is not built yet"
          description="Contracts, scopes of work, inspection reports and title documents will live here."
          planned={[
            "Upload and version contracts and addenda",
            "Attach contractor bids to a rehab estimate",
            "Link a document to the assumption it supports",
          ]}
        />
      )}
      {tab === "AI Analysis" &&
        (current ? (
          <AiAnalysisTab analysis={current} onRefresh={setCurrent} />
        ) : (
          <NoAnalysis onGo={() => setTab("Financials")} />
        ))}
    </>
  );
}

function NoAnalysis({ onGo }: { onGo: () => void }) {
  return (
    <EmptyState
      title="No analysis saved yet"
      description="Enter the numbers on the Financials tab and save an analysis to populate this view."
      action={
        <button type="button" className="btn-primary" onClick={onGo}>
          Go to Financials
        </button>
      }
    />
  );
}

function OverviewTab({
  property,
  analyses,
  current,
}: {
  property: Property;
  analyses: AnalysisSummary[];
  current: AnalysisResponse | null;
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="card">
        <div className="card-header">
          <h2 className="card-title">Property</h2>
        </div>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 px-4 py-4 text-sm">
          <Detail label="Type" value={property.property_type ? humanise(property.property_type) : EMPTY} />
          <Detail label="Bedrooms" value={formatNumber(property.bedrooms)} />
          <Detail label="Bathrooms" value={formatNumber(property.bathrooms)} />
          <Detail label="Square feet" value={formatNumber(property.square_feet)} />
          <Detail label="Lot size" value={formatNumber(property.lot_size)} />
          <Detail label="Year built" value={property.year_built?.toString() ?? EMPTY} />
          <Detail label="County" value={property.county ?? EMPTY} />
          <Detail label="Parcel / APN" value={property.parcel_apn ?? EMPTY} />
          <Detail label="Estimated value" value={formatMoney(property.estimated_value)} />
          <Detail label="Estimated rent" value={formatMoney(property.estimated_rent)} />
        </dl>
        {property.notes && (
          <div className="border-t border-ink-200 px-4 py-3">
            <p className="label mb-1">Notes</p>
            <p className="whitespace-pre-wrap text-sm text-ink-700">{property.notes}</p>
          </div>
        )}
      </div>

      <div className="space-y-4">
        {current ? (
          <ScorePanel scoring={current.scoring} />
        ) : (
          <EmptyState
            title="Not analyzed yet"
            description="Use the Financials tab to underwrite this property across every strategy."
          />
        )}

        <div className="card">
          <div className="card-header">
            <h2 className="card-title">Saved analyses</h2>
          </div>
          {analyses.length === 0 ? (
            <p className="px-4 py-4 text-sm text-ink-500">None saved.</p>
          ) : (
            <ul className="divide-y divide-ink-100">
              {analyses.map((analysis) => (
                <li key={analysis.id} className="flex items-center justify-between px-4 py-2.5">
                  <div>
                    <p className="text-sm text-ink-800">{analysis.name ?? "Analysis"}</p>
                    <p className="text-[11px] text-ink-500">
                      {formatDateTime(analysis.created_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <ConfidenceBadge confidence={analysis.confidence} label={false} />
                    <VerdictBadge verdict={analysis.verdict} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="label">{label}</dt>
      <dd className="tabular mt-0.5 text-ink-900">{value}</dd>
    </div>
  );
}

function OwnerTab({ propertyId }: { propertyId: string }) {
  const [owners, setOwners] = useState<Owner[] | null>(null);

  useEffect(() => {
    // Must go through the API client: it attaches the Supabase bearer token.
    // A bare fetch() here works only under development auth and 401s the
    // moment real authentication is enabled.
    api.listOwners(propertyId).then(setOwners).catch(() => setOwners([]));
  }, [propertyId]);

  if (!owners) return <LoadingState />;

  return (
    <div className="space-y-4">
      <div className="card px-4 py-3 text-sm text-ink-600">
        Ownership facts are recorded here as observations. Atlas does not infer seller
        motivation from absentee ownership or high equity — those are classifications of a
        situation, not evidence that someone wants to sell.
      </div>
      {owners.length === 0 ? (
        <EmptyState
          title="No ownership record"
          description="Owner details can be entered manually or imported from a data provider when one is connected."
        />
      ) : (
        <div className="card">
          <ul className="divide-y divide-ink-100">
            {owners.map((owner) => (
              <li key={owner.id} className="px-4 py-3 text-sm">
                <p className="font-medium text-ink-900">{owner.owner_name ?? EMPTY}</p>
                <dl className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <Detail label="Entity type" value={owner.entity_type ?? EMPTY} />
                  <Detail label="Occupancy" value={owner.occupancy_indicator ? humanise(owner.occupancy_indicator) : EMPTY} />
                  <Detail label="Estimated equity" value={formatMoney(owner.estimated_equity)} />
                  <Detail label="Estimated mortgage" value={formatMoney(owner.estimated_mortgage)} />
                </dl>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ListingTab({ property }: { property: Property }) {
  return (
    <div className="card">
      <div className="card-header">
        <h2 className="card-title">Listing</h2>
      </div>
      <dl className="grid grid-cols-2 gap-4 px-4 py-4 text-sm sm:grid-cols-4">
        <Detail label="Listing price" value={formatMoney(property.listing_price)} />
        <Detail label="Days on market" value={property.days_on_market?.toString() ?? EMPTY} />
        <Detail label="Status" value={humanise(property.property_status)} />
        <Detail label="Last updated" value={formatDate(property.updated_at)} />
      </dl>
      <p className="border-t border-ink-200 px-4 py-3 text-xs text-ink-500">
        A listing price is an asking figure, not a value. Atlas treats it as an
        INFERENCE when it is used to support an ARV, and rates that ARV LOW confidence.
      </p>
    </div>
  );
}

function CompsTab({ propertyId }: { propertyId: string }) {
  const [comps, setComps] = useState<Comp[] | null>(null);

  useEffect(() => {
    api.listComps(propertyId).then(setComps).catch(() => setComps([]));
  }, [propertyId]);

  if (!comps) return <LoadingState />;
  if (comps.length === 0) {
    return (
      <EmptyState
        title="No comparable sales recorded"
        description="ARV confidence depends on these. Four or more recent, highly similar closed sales support a HIGH confidence value; fewer than two support only LOW."
      />
    );
  }

  return (
    <div className="card overflow-x-auto">
      <table className="table tabular min-w-[760px]">
        <thead>
          <tr>
            <th>Address</th>
            <th>Sale price</th>
            <th>Sale date</th>
            <th>Beds</th>
            <th>Baths</th>
            <th>Sq ft</th>
            <th>$/sq ft</th>
            <th>Similarity</th>
          </tr>
        </thead>
        <tbody>
          {comps.map((comp) => (
            <tr key={comp.id}>
              <td className="font-medium text-ink-900">{comp.address}</td>
              <td>{formatMoney(comp.sale_price)}</td>
              <td>{formatDate(comp.sale_date)}</td>
              <td>{formatNumber(comp.bedrooms)}</td>
              <td>{formatNumber(comp.bathrooms)}</td>
              <td>{formatNumber(comp.square_feet)}</td>
              <td>{formatMoney(comp.price_per_square_foot, { decimals: 0 })}</td>
              <td>{formatPercent(comp.similarity_score, 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * The financials tab. Seeds the editor from the most recent saved analysis so
 * changing an assumption starts from where underwriting was left, not from a
 * blank form.
 */
function FinancialsTab({
  property,
  current,
  onSaved,
}: {
  property: Property;
  current: AnalysisResponse | null;
  onSaved: (analysis: AnalysisResponse) => void;
}) {
  const state = useAnalysis(draftFromAnalysis(current));
  const { setDraft } = state;
  // The saved analysis arrives after the first render, so the editor is
  // re-seeded when a DIFFERENT analysis loads. Keyed on the id rather than the
  // object: re-seeding on every change would discard what the user is typing,
  // and remounting the tab would throw away the save confirmation.
  const seededAnalysisId = useRef<string | null | undefined>(current?.id);
  useEffect(() => {
    if (current?.id !== seededAnalysisId.current) {
      seededAnalysisId.current = current?.id;
      setDraft(draftFromAnalysis(current));
    }
  }, [current, setDraft]);

  const [saving, setSaving] = useState(false);
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [audit, setAudit] = useState<AssumptionAudit[]>([]);

  const analysisId = current?.id ?? null;

  const loadAudit = useCallback(() => {
    if (!analysisId) return;
    api.getAuditTrail(analysisId).then(setAudit).catch(() => setAudit([]));
  }, [analysisId]);

  useEffect(loadAudit, [loadAudit]);

  async function save() {
    setSaving(true);
    setMessage(null);
    try {
      const payload = {
        ...draftToRequest(state.draft),
        name: current?.name ?? "Underwriting",
        change_reason: reason || undefined,
      };
      const result = analysisId
        ? await api.updateAnalysis(analysisId, payload)
        : await api.saveAnalysis(property.id, payload);
      onSaved(result);
      setReason("");
      setMessage("Saved. Assumption changes were recorded in the audit trail.");
      loadAudit();
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-5">
      <AnalysisWorkspace
        state={state}
        header={
          <div className="card px-4 py-3">
            <label className="label" htmlFor="change-reason">
              Reason for this change
            </label>
            <input
              id="change-reason"
              className="input mt-1"
              placeholder="e.g. Two newer comps closed higher"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
            <p className="mt-1 text-[11px] text-ink-500">
              Recorded against every assumption you changed, with the previous and new
              value.
            </p>
            <button
              type="button"
              className="btn-primary mt-3 w-full"
              onClick={save}
              disabled={saving || !state.analysis}
            >
              {saving ? "Saving…" : analysisId ? "Save changes" : "Save analysis"}
            </button>
            {message && <p className="mt-2 text-[11px] text-ink-600">{message}</p>}
          </div>
        }
      />

      {audit.length > 0 && (
        <div className="card">
          <div className="card-header">
            <h2 className="card-title">Assumption audit trail</h2>
            <span className="text-xs text-ink-500">
              Underwriting assumptions change. This is the record of when and why.
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="table tabular min-w-[720px]">
              <thead>
                <tr>
                  <th>Assumption</th>
                  <th>From</th>
                  <th>To</th>
                  <th>Reason</th>
                  <th>Changed</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((entry) => (
                  <tr key={entry.id}>
                    <td className="font-medium text-ink-900">
                      {entry.field_label ?? entry.field_path}
                    </td>
                    <td className="text-ink-500">{entry.previous_value ?? EMPTY}</td>
                    <td>{entry.new_value ?? EMPTY}</td>
                    <td className="text-ink-600">{entry.reason ?? EMPTY}</td>
                    <td className="whitespace-nowrap text-[11px] text-ink-500">
                      {formatDateTime(entry.changed_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function AiAnalysisTab({
  analysis,
  onRefresh,
}: {
  analysis: AnalysisResponse;
  onRefresh: (analysis: AnalysisResponse) => void;
}) {
  const [generating, setGenerating] = useState(false);

  async function generate() {
    if (!analysis.id) return;
    setGenerating(true);
    try {
      onRefresh(await api.generateAiAnalysis(analysis.id));
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-center justify-between gap-3 px-4 py-3">
        <p className="max-w-2xl text-sm text-ink-600">
          The agents receive the completed calculations and interpret them. They do not
          perform arithmetic, and nothing here changes a number shown elsewhere.
        </p>
        <button type="button" className="btn-secondary" onClick={generate} disabled={generating}>
          {generating ? "Generating…" : analysis.ai_analysis ? "Regenerate" : "Generate"}
        </button>
      </div>
      <AiPanel analysis={analysis} />
    </div>
  );
}

function CommunicationsTab({ propertyId }: { propertyId: string }) {
  const [items, setItems] = useState<Communication[] | null>(null);
  const [form, setForm] = useState({ communication_type: "call", direction: "outbound", notes: "", outcome: "" });
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    api.listCommunications(propertyId).then(setItems).catch(() => setItems([]));
  }, [propertyId]);

  useEffect(load, [load]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      await api.createCommunication(propertyId, {
        communication_type: form.communication_type,
        direction: form.direction,
        notes: form.notes || null,
        outcome: form.outcome || null,
      });
      setForm({ ...form, notes: "", outcome: "" });
      load();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
      <form onSubmit={submit} className="card px-4 py-4">
        <h2 className="card-title mb-3">Log a communication</h2>
        <div className="space-y-3">
          <div>
            <label className="label" htmlFor="comm-type">Type</label>
            <select
              id="comm-type"
              className="input mt-1"
              value={form.communication_type}
              onChange={(event) => setForm({ ...form, communication_type: event.target.value })}
            >
              <option value="call">Call</option>
              <option value="text">Text</option>
              <option value="email">Email</option>
              <option value="letter">Letter</option>
              <option value="door_knock">Door knock</option>
              <option value="meeting">Meeting</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="comm-direction">Direction</label>
            <select
              id="comm-direction"
              className="input mt-1"
              value={form.direction}
              onChange={(event) => setForm({ ...form, direction: event.target.value })}
            >
              <option value="outbound">Outbound</option>
              <option value="inbound">Inbound</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="comm-outcome">Outcome</label>
            <input
              id="comm-outcome"
              className="input mt-1"
              value={form.outcome}
              onChange={(event) => setForm({ ...form, outcome: event.target.value })}
            />
          </div>
          <div>
            <label className="label" htmlFor="comm-notes">Notes</label>
            <textarea
              id="comm-notes"
              className="input mt-1 min-h-[80px]"
              value={form.notes}
              onChange={(event) => setForm({ ...form, notes: event.target.value })}
            />
          </div>
          <button type="submit" className="btn-primary w-full" disabled={saving}>
            {saving ? "Saving…" : "Log it"}
          </button>
        </div>
      </form>

      <div className="card">
        <div className="card-header">
          <h2 className="card-title">History</h2>
        </div>
        {!items ? (
          <LoadingState />
        ) : items.length === 0 ? (
          <p className="px-4 py-4 text-sm text-ink-500">Nothing logged yet.</p>
        ) : (
          <ul className="divide-y divide-ink-100">
            {items.map((item) => (
              <li key={item.id} className="px-4 py-3 text-sm">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-medium text-ink-900">
                    {humanise(item.communication_type)} · {item.direction}
                  </span>
                  <span className="text-[11px] text-ink-500">
                    {formatDateTime(item.occurred_at)}
                  </span>
                </div>
                {item.outcome && <p className="text-xs text-ink-600">{item.outcome}</p>}
                {item.notes && <p className="mt-1 text-sm text-ink-700">{item.notes}</p>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/** Rebuild an editable draft from a saved analysis. */
function draftFromAnalysis(analysis: AnalysisResponse | null): Draft {
  if (!analysis) return EMPTY_DRAFT;
  const inputs = (analysis.inputs ?? {}) as Record<string, any>;
  const value = (key: string) =>
    inputs[key] === null || inputs[key] === undefined ? "" : String(inputs[key]);
  return {
    purchase_price: value("purchase_price"),
    arv: value("arv"),
    arv_low: value("arv_low"),
    arv_high: value("arv_high"),
    rehab: value("rehab"),
    rehab_low: value("rehab_low"),
    rehab_high: value("rehab_high"),
    monthly_rent: value("monthly_rent"),
    evidence: (inputs.evidence ?? {}) as Draft["evidence"],
    assumptions: (inputs.assumptions ?? {}) as Record<string, any>,
    risk_flags: (inputs.risk_flags ?? []) as string[],
  };
}
