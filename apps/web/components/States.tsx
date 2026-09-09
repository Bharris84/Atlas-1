export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="card px-4 py-10 text-center text-sm text-ink-500">{label}</div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="card border-fail-500/30 px-4 py-6 text-center">
      <p className="text-sm font-medium text-fail-700">{message}</p>
      {onRetry && (
        <button type="button" className="btn-secondary mt-3" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="card px-4 py-10 text-center">
      <p className="text-sm font-medium text-ink-800">{title}</p>
      <p className="mx-auto mt-1 max-w-md text-sm text-ink-500">{description}</p>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

/**
 * A feature that is deliberately not built yet.
 *
 * Shown instead of a fake screen: a mock that looks functional is worse than an
 * honest note about what exists and what does not.
 */
export function PlannedFeature({
  title,
  description,
  planned,
}: {
  title: string;
  description: string;
  planned: string[];
}) {
  return (
    <div className="card px-5 py-6">
      <p className="text-sm font-semibold text-ink-900">{title}</p>
      <p className="mt-1 max-w-2xl text-sm text-ink-600">{description}</p>
      <p className="mt-4 label">Planned for this section</p>
      <ul className="mt-2 space-y-1 text-sm text-ink-600">
        {planned.map((item) => (
          <li key={item} className="flex gap-2">
            <span className="text-ink-300">&bull;</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function StatTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="card px-4 py-3">
      <p className="label">{label}</p>
      <p className="tabular mt-1 text-xl font-semibold text-ink-900">{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-ink-500">{hint}</p>}
    </div>
  );
}
