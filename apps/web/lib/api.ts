/**
 * API client.
 *
 * Requests go from the browser to the Atlas backend. No API key of any kind
 * appears here: the RentCast key, the AI provider key and the database URL all
 * live on the backend and are never sent to the browser.
 */

import type {
  AnalysisRequest,
  AnalysisResponse,
  AnalysisSummary,
  AssumptionAudit,
  Comp,
  Communication,
  Dashboard,
  Lead,
  Offer,
  Property,
  PropertySummary,
  RehabProject,
  SystemStatus,
  UserSettings,
} from "@atlas/shared-types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly detail?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Supabase issues the access token; the backend verifies it. When Supabase is
 * not configured the backend runs in development mode and accepts requests
 * without one.
 */
function authHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = window.localStorage.getItem("atlas.access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...(init.headers ?? {}),
      },
      cache: "no-store",
    });
  } catch (cause) {
    throw new ApiError(
      `Cannot reach the Atlas API at ${API_URL}. Is the backend running?`,
      0,
      cause
    );
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const body = text ? safeParse(text) : null;

  if (!response.ok) {
    throw new ApiError(extractMessage(body, response.status), response.status, body);
  }
  return body as T;
}

function safeParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function extractMessage(body: unknown, status: number): string {
  if (typeof body === "string" && body) return body;
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    // FastAPI validation errors arrive as an array of field-level problems.
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (item && typeof item === "object" && "msg" in item) {
            const location = Array.isArray((item as any).loc)
              ? (item as any).loc.filter((p: unknown) => p !== "body").join(".")
              : "";
            return location ? `${location}: ${(item as any).msg}` : String((item as any).msg);
          }
          return String(item);
        })
        .join("; ");
    }
  }
  return `Request failed with status ${status}.`;
}

const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) });

export const api = {
  // --- System -------------------------------------------------------------
  status: () => request<SystemStatus>("/api/status"),
  dashboard: () => request<Dashboard>("/api/dashboard"),

  // --- Properties ---------------------------------------------------------
  listProperties: (params: Record<string, string | undefined> = {}) => {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v) as [string, string][]
    ).toString();
    return request<PropertySummary[]>(`/api/properties${query ? `?${query}` : ""}`);
  },
  getProperty: (id: string) => request<Property>(`/api/properties/${id}`),
  createProperty: (body: Partial<Property>) =>
    request<Property>("/api/properties", { method: "POST", ...json(body) }),
  updateProperty: (id: string, body: Partial<Property>) =>
    request<Property>(`/api/properties/${id}`, { method: "PATCH", ...json(body) }),
  deleteProperty: (id: string) =>
    request<void>(`/api/properties/${id}`, { method: "DELETE" }),
  enrichProperty: (id: string) =>
    request<{
      provider: string;
      imported: string[];
      unavailable: string[];
      detail: string;
    }>(`/api/properties/${id}/enrich`, { method: "POST" }),

  // --- Analysis -----------------------------------------------------------
  analyze: (body: AnalysisRequest) =>
    request<AnalysisResponse>("/api/analyze", { method: "POST", ...json(body) }),
  listAnalyses: (propertyId: string) =>
    request<AnalysisSummary[]>(`/api/properties/${propertyId}/analyses`),
  saveAnalysis: (propertyId: string, body: AnalysisRequest) =>
    request<AnalysisResponse>(`/api/properties/${propertyId}/analyses`, {
      method: "POST",
      ...json(body),
    }),
  getAnalysis: (id: string) => request<AnalysisResponse>(`/api/analyses/${id}`),
  updateAnalysis: (id: string, body: AnalysisRequest) =>
    request<AnalysisResponse>(`/api/analyses/${id}`, { method: "PUT", ...json(body) }),
  deleteAnalysis: (id: string) =>
    request<void>(`/api/analyses/${id}`, { method: "DELETE" }),
  getAuditTrail: (id: string) =>
    request<AssumptionAudit[]>(`/api/analyses/${id}/audit`),
  generateAiAnalysis: (id: string) =>
    request<AnalysisResponse>(`/api/analyses/${id}/ai`, { method: "POST" }),

  // --- Related records ----------------------------------------------------
  listComps: (propertyId: string) =>
    request<Comp[]>(`/api/properties/${propertyId}/comps`),
  createComp: (propertyId: string, body: Partial<Comp>) =>
    request<Comp>(`/api/properties/${propertyId}/comps`, { method: "POST", ...json(body) }),
  deleteComp: (propertyId: string, compId: string) =>
    request<void>(`/api/properties/${propertyId}/comps/${compId}`, { method: "DELETE" }),
  listOffers: (propertyId: string) =>
    request<Offer[]>(`/api/properties/${propertyId}/offers`),
  createOffer: (propertyId: string, body: Partial<Offer>) =>
    request<Offer>(`/api/properties/${propertyId}/offers`, {
      method: "POST",
      ...json(body),
    }),
  listCommunications: (propertyId: string) =>
    request<Communication[]>(`/api/properties/${propertyId}/communications`),
  createCommunication: (propertyId: string, body: Partial<Communication>) =>
    request<Communication>(`/api/properties/${propertyId}/communications`, {
      method: "POST",
      ...json(body),
    }),
  listRehabProjects: (propertyId: string) =>
    request<RehabProject[]>(`/api/properties/${propertyId}/rehab-projects`),
  createRehabProject: (propertyId: string, body: Partial<RehabProject>) =>
    request<RehabProject>(`/api/properties/${propertyId}/rehab-projects`, {
      method: "POST",
      ...json(body),
    }),

  // --- Leads --------------------------------------------------------------
  listLeads: (params: Record<string, string | undefined> = {}) => {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v) as [string, string][]
    ).toString();
    return request<Lead[]>(`/api/leads${query ? `?${query}` : ""}`);
  },
  createLead: (body: Partial<Lead> & { property_id: string }) =>
    request<Lead>("/api/leads", { method: "POST", ...json(body) }),
  updateLead: (id: string, body: Partial<Lead>) =>
    request<Lead>(`/api/leads/${id}`, { method: "PATCH", ...json(body) }),
  deleteLead: (id: string) => request<void>(`/api/leads/${id}`, { method: "DELETE" }),

  // --- Settings -----------------------------------------------------------
  getSettings: () => request<UserSettings>("/api/settings"),
  updateSettings: (body: {
    display_name?: string;
    default_assumptions?: Record<string, unknown>;
  }) => request<UserSettings>("/api/settings", { method: "PUT", ...json(body) }),
  resetSettings: () => request<UserSettings>("/api/settings/reset", { method: "POST" }),
};
