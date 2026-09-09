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
import type { SystemStatus, UserSettings } from "@atlas/shared-types";

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
      const result = await api.updateSettings({ default_assumptions: draft });
      setSettings(result);
      setDraft(result.default_assumptions);
      setMessage("Buy box saved. New analyses will start from these values.");
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
      setMessage("Restored the engine's provisional defaults.");
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
              {saving ? "Saving…" : "Save buy box"}
            </button>
          </>
        }
      />

      {message && <p className="mb-4 text-sm text-ink-600">{message}</p>}

      <div className="mb-5 card border-caution-500/30 bg-caution-50 px-4 py-3 text-sm text-caution-700">
        {settings.provisional_defaults_note}
      </div>

      <div className="space-y-4">
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
