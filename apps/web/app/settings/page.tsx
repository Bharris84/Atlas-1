"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "@/components/Shell";
import { ErrorState, LoadingState } from "@/components/States";
import {
  ASSUMPTION_GROUPS,
  getPath,
  setPath,
  toApiValue,
  toDisplayValue,
  unitSuffix,
} from "@/lib/assumptions";
import { api } from "@/lib/api";
import { STRATEGY_LABELS, STRATEGY_ORDER } from "@atlas/shared-types";
import type {
  InvestorProfile,
  StrategyKey,
  SystemStatus,
  UserSettings,
} from "@atlas/shared-types";

/**
 * The investor profile is deliberately a separate card from the buy box.
 * The buy box says how a DEAL is underwritten; this says what the INVESTOR can
 * actually do. Conflating them is how a tool ends up recommending deals its
 * user cannot fund.
 */
const PROFILE_FIELDS: {
  key: keyof InvestorProfile;
  label: string;
  kind: "money" | "percent";
  help?: string;
}[] = [
  {
    key: "available_capital",
    label: "Available capital",
    kind: "money",
    help: "Total liquid capital. Left blank it stays unknown, never zero.",
  },
  {
    key: "max_capital_deployment",
    label: "Max per deal",
    kind: "money",
    help: "The most you will commit to a single property.",
  },
  { key: "preferred_minimum_cash_flow", label: "Minimum cash flow", kind: "money" },
  { key: "minimum_roi", label: "Minimum ROI", kind: "percent" },
  { key: "max_cash_left_in_deal", label: "Max cash left in deal", kind: "money" },
  {
    key: "minimum_wholesale_assignment",
    label: "Minimum assignment fee",
    kind: "money",
  },
];

/**
 * The buy box.
 *
 * These become the starting point for every new analysis. They are still
 * provisional defaults — any individual deal can override them, and that
 * override is what the audit trail records.
 */
export default function SettingsPage() {
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [draft, setDraft] = useState<Record<string, any>>({});
  const [profileDraft, setProfileDraft] = useState<Record<string, any>>({});
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = () => {
    setError(null);
    api
      .getSettings()
      .then((result) => {
        setSettings(result);
        setDraft(result.default_assumptions);
        setProfileDraft(result.investor_profile as unknown as Record<string, any>);
      })
      .catch((cause) =>
        setError(cause instanceof Error ? cause.message : "Could not load settings.")
      );
    api.status().then(setStatus).catch(() => setStatus(null));
  };

  useEffect(load, []);

  async function save() {
    setSaving(true);
    setMessage(null);
    try {
      const result = await api.updateSettings({
        default_assumptions: draft,
        investor_profile: profileDraft,
      });
      setSettings(result);
      setDraft(result.default_assumptions);
      setProfileDraft(result.investor_profile as unknown as Record<string, any>);
      setMessage("Saved. New analyses will start from these values.");
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  async function reset() {
    setSaving(true);
    try {
      const result = await api.resetSettings();
      setSettings(result);
      setDraft(result.default_assumptions);
      setProfileDraft(result.investor_profile as unknown as Record<string, any>);
      setMessage("Restored the provisional defaults and cleared the investor profile.");
    } finally {
      setSaving(false);
    }
  }

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!settings) return <LoadingState label="Loading settings…" />;

  return (
    <>
      <PageHeader
        title="Settings"
        description="Your buy box and the state of every external connection."
        actions={
          <>
            <button type="button" className="btn-secondary" onClick={reset} disabled={saving}>
              Restore defaults
            </button>
            <button type="button" className="btn-primary" onClick={save} disabled={saving}>
              {saving ? "Saving…" : "Save settings"}
            </button>
          </>
        }
      />

      {message && <p className="mb-4 text-sm text-ink-600">{message}</p>}

      <div className="mb-5 card border-caution-500/30 bg-caution-50 px-4 py-3 text-sm text-caution-700">
        {settings.provisional_defaults_note}
      </div>

      <div className="space-y-4">
        <div className="card">
          <div className="card-header">
            <div>
              <h2 className="card-title">Investor profile</h2>
              <p className="mt-0.5 max-w-2xl text-xs text-ink-500">
                This describes you, not a property: what capital exists and what returns
                are acceptable. It is kept separate from the buy box below, which describes
                how a deal is underwritten.
              </p>
            </div>
          </div>

          <div className="grid gap-3 px-4 py-4 sm:grid-cols-2 lg:grid-cols-3">
            {PROFILE_FIELDS.map((field) => (
              <div key={field.key as string}>
                <label className="label" htmlFor={`profile-${String(field.key)}`}>
                  {field.label}
                </label>
                <input
                  id={`profile-${String(field.key)}`}
                  className="input tabular mt-1"
                  inputMode="decimal"
                  placeholder="not stated"
                  value={toDisplayValue(profileDraft[field.key as string], field.kind)}
                  onChange={(event) => {
                    const value = toApiValue(event.target.value, field.kind);
                    setProfileDraft((current) => ({
                      ...current,
                      // Empty means unstated, which is not the same as zero.
                      [field.key as string]: value,
                    }));
                  }}
                />
                {field.help && <p className="mt-1 text-[11px] text-ink-500">{field.help}</p>}
              </div>
            ))}

            <div>
              <label className="label" htmlFor="profile-risk">
                Risk tolerance
              </label>
              <select
                id="profile-risk"
                className="input mt-1"
                value={profileDraft.risk_tolerance ?? "moderate"}
                onChange={(event) =>
                  setProfileDraft((c) => ({ ...c, risk_tolerance: event.target.value }))
                }
              >
                <option value="conservative">Conservative</option>
                <option value="moderate">Moderate</option>
                <option value="aggressive">Aggressive</option>
              </select>
            </div>

            <div>
              <label className="label" htmlFor="profile-capital-pref">
                Capital preference
              </label>
              <select
                id="profile-capital-pref"
                className="input mt-1"
                value={profileDraft.capital_efficiency_preference ?? "balanced"}
                onChange={(event) =>
                  setProfileDraft((c) => ({
                    ...c,
                    capital_efficiency_preference: event.target.value,
                  }))
                }
              >
                <option value="maximize_velocity">Get capital back quickly</option>
                <option value="balanced">Balanced</option>
                <option value="maximize_absolute_profit">Maximise absolute profit</option>
              </select>
              <p className="mt-1 text-[11px] text-ink-500">
                Recorded now; it does not yet change the ranking.
              </p>
            </div>
          </div>

          <div className="border-t border-ink-200 px-4 py-3">
            <p className="label mb-2">Preferred strategies</p>
            <div className="flex flex-wrap gap-3">
              {STRATEGY_ORDER.map((strategy) => {
                const selected: StrategyKey[] = profileDraft.preferred_strategies ?? [];
                const checked = selected.includes(strategy);
                return (
                  <label
                    key={strategy}
                    className="flex items-center gap-2 text-sm text-ink-700"
                  >
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-ink-300 text-ink-900 focus:ring-ink-500"
                      checked={checked}
                      onChange={() =>
                        setProfileDraft((c) => ({
                          ...c,
                          preferred_strategies: checked
                            ? selected.filter((s) => s !== strategy)
                            : [...selected, strategy],
                        }))
                      }
                    />
                    {STRATEGY_LABELS[strategy]}
                  </label>
                );
              })}
            </div>
            <p className="mt-2 text-[11px] text-ink-500">
              Selecting none means no preference, not that nothing is acceptable.
            </p>
          </div>

          {settings.provisional_profile_note && (
            <p className="border-t border-ink-200 bg-ink-50 px-4 py-3 text-[11px] text-ink-500">
              {settings.provisional_profile_note}
            </p>
          )}
        </div>

        {ASSUMPTION_GROUPS.map((group) => (
          <div key={group.key} className="card">
            <div className="card-header">
              <div>
                <h2 className="card-title">{group.title}</h2>
                <p className="mt-0.5 max-w-2xl text-xs text-ink-500">{group.description}</p>
              </div>
            </div>
            <div className="grid gap-3 px-4 py-4 sm:grid-cols-2 lg:grid-cols-4">
              {group.fields.map((field) => (
                <div key={field.path}>
                  <label className="label" htmlFor={field.path} title={field.help}>
                    {field.label}
                  </label>
                  <div className="relative mt-1">
                    <input
                      id={field.path}
                      className="input tabular pr-8"
                      inputMode="decimal"
                      value={toDisplayValue(getPath(draft, field.path), field.kind)}
                      onChange={(event) => {
                        const value = toApiValue(event.target.value, field.kind);
                        setDraft((current) =>
                          setPath(current, field.path, value === null ? "" : value)
                        );
                      }}
                    />
                    <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-ink-400">
                      {unitSuffix(field.kind)}
                    </span>
                  </div>
                  {field.help && <p className="mt-1 text-[11px] text-ink-500">{field.help}</p>}
                </div>
              ))}
            </div>
          </div>
        ))}

        {status && (
          <div className="card">
            <div className="card-header">
              <h2 className="card-title">Connections</h2>
              <span className="text-xs text-ink-500">
                Keys live on the backend and are never sent to this page
              </span>
            </div>
            <div className="divide-y divide-ink-100">
              <Connection
                name="Database"
                configured={status.database !== "sqlite"}
                detail={
                  status.database === "sqlite"
                    ? "Local SQLite file. Set ATLAS_DATABASE_URL to use PostgreSQL or Supabase."
                    : "PostgreSQL connected."
                }
              />
              <Connection
                name="Authentication"
                configured={status.authentication === "supabase"}
                detail={
                  status.authentication === "supabase"
                    ? "Supabase Auth verifying tokens."
                    : "Development identity. Set SUPABASE_JWT_SECRET before exposing this API — production refuses to start without it."
                }
              />
              <Connection
                name={`AI (${status.ai_provider.name})`}
                configured={status.ai_provider.name !== "null"}
                detail={status.ai_provider.detail}
              />
              {status.data_providers.map((provider) => (
                <Connection
                  key={provider.name}
                  name={`Data — ${provider.name}`}
                  configured={provider.configured}
                  detail={provider.detail}
                />
              ))}
            </div>
            <p className="border-t border-ink-200 px-4 py-3 text-[11px] text-ink-500">
              Atlas runs with none of these configured. The financial engine works entirely
              on manually entered data.
            </p>
          </div>
        )}
      </div>
    </>
  );
}

function Connection({
  name,
  configured,
  detail,
}: {
  name: string;
  configured: boolean;
  detail: string;
}) {
  return (
    <div className="flex items-start justify-between gap-4 px-4 py-3">
      <div className="min-w-0">
        <p className="text-sm font-medium text-ink-900">{name}</p>
        <p className="mt-0.5 text-xs text-ink-500">{detail}</p>
      </div>
      <span
        className={`shrink-0 rounded px-2 py-0.5 text-[11px] font-semibold uppercase ${
          configured ? "bg-pass-100 text-pass-700" : "bg-ink-200 text-ink-600"
        }`}
      >
        {configured ? "Connected" : "Not set"}
      </span>
    </div>
  );
}
