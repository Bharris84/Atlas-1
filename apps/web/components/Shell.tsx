"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { SystemStatus } from "@atlas/shared-types";

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/properties", label: "Properties" },
  { href: "/analyzer", label: "Analyzer" },
  { href: "/leads", label: "Leads" },
  { href: "/deals", label: "Deals" },
  { href: "/markets", label: "Markets" },
  { href: "/contacts", label: "Contacts" },
  { href: "/projects", label: "Projects" },
  { href: "/settings", label: "Settings" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    api
      .status()
      .then(setStatus)
      .catch(() => setOffline(true));
  }, []);

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-ink-200 bg-white lg:flex">
        <div className="border-b border-ink-200 px-5 py-4">
          <Link href="/" className="block">
            <div className="text-lg font-semibold tracking-tight text-ink-900">Atlas</div>
            <div className="text-[11px] text-ink-500">Investment intelligence</div>
          </Link>
        </div>

        <nav className="flex-1 space-y-0.5 p-3">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`block rounded-md px-3 py-2 text-sm transition ${
                isActive(item.href)
                  ? "bg-ink-900 font-medium text-white"
                  : "text-ink-600 hover:bg-ink-100 hover:text-ink-900"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="space-y-1 border-t border-ink-200 p-3 text-[11px] text-ink-500">
          {offline ? (
            <p className="text-fail-600">API unreachable</p>
          ) : status ? (
            <>
              <p>Engine v{status.engine_version}</p>
              <p>
                AI:{" "}
                {status.ai_provider.name === "null"
                  ? "deterministic"
                  : status.ai_provider.name}
              </p>
              <p>
                Data:{" "}
                {status.data_providers.some((p) => p.configured)
                  ? "provider connected"
                  : "manual entry"}
              </p>
              {status.authentication === "development" && (
                <p className="text-caution-600">Dev auth</p>
              )}
            </>
          ) : (
            <p>Connecting…</p>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-4 overflow-x-auto border-b border-ink-200 bg-white px-4 py-2 lg:hidden">
          <Link href="/" className="text-base font-semibold text-ink-900">
            Atlas
          </Link>
          <nav className="flex gap-3">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`whitespace-nowrap text-sm ${
                  isActive(item.href)
                    ? "font-medium text-ink-900"
                    : "text-ink-500"
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </header>

        <main className="flex-1 p-4 lg:p-6">{children}</main>
      </div>
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-ink-900">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-ink-500">{description}</p>}
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  );
}
