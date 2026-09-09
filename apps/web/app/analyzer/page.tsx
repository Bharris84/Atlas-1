"use client";

import Link from "next/link";
import { useState } from "react";

import { AnalysisWorkspace } from "@/components/AnalysisWorkspace";
import { PageHeader } from "@/components/Shell";
import { EMPTY_DRAFT, useAnalysis } from "@/hooks/useAnalysis";
import { api } from "@/lib/api";
import type { PropertySummary } from "@atlas/shared-types";
import { useEffect } from "react";

/**
 * The deal analyzer: numbers in, five strategies out, nothing saved unless
 * asked. This is the fastest path from "here is a property" to "is it worth
 * pursuing, and how".
 */
export default function AnalyzerPage() {
  const state = useAnalysis(EMPTY_DRAFT);
  const [properties, setProperties] = useState<PropertySummary[]>([]);
  const [saveTo, setSaveTo] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<{ id: string; propertyId: string } | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    api.listProperties().then(setProperties).catch(() => setProperties([]));
  }, []);

  async function save() {
    if (!saveTo) return;
    setSaving(true);
    setSaveError(null);
    try {
      const { draftToRequest } = await import("@/hooks/useAnalysis");
      const result = await api.saveAnalysis(saveTo, {
        ...draftToRequest(state.draft),
        name: "Analyzer run",
        change_reason: "Saved from the deal analyzer",
      });
      setSaved({ id: result.id as string, propertyId: saveTo });
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Deal analyzer"
        description="Enter what you know. Atlas underwrites wholesale, flip, buy & hold, BRRRR and seller financing side by side, and recomputes as you change any assumption."
      />

      <AnalysisWorkspace
        state={state}
        header={
          <div className="card px-4 py-3">
            <label className="label" htmlFor="save-target">
              Save this analysis to a property
            </label>
            <div className="mt-1 flex gap-2">
              <select
                id="save-target"
                className="input"
                value={saveTo}
                onChange={(event) => {
                  setSaveTo(event.target.value);
                  setSaved(null);
                }}
              >
                <option value="">Not saved</option>
                {properties.map((property) => (
                  <option key={property.id} value={property.id}>
                    {property.address}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="btn-primary whitespace-nowrap"
                disabled={!saveTo || saving || !state.analysis}
                onClick={save}
              >
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
            {properties.length === 0 && (
              <p className="mt-2 text-[11px] text-ink-500">
                No properties yet.{" "}
                <Link href="/properties/new" className="underline">
                  Create one
                </Link>{" "}
                to save an analysis against it.
              </p>
            )}
            {saved && (
              <p className="mt-2 text-[11px] text-pass-700">
                Saved.{" "}
                <Link href={`/properties/${saved.propertyId}`} className="underline">
                  Open the property
                </Link>
              </p>
            )}
            {saveError && <p className="mt-2 text-[11px] text-fail-600">{saveError}</p>}
          </div>
        }
      />
    </>
  );
}
