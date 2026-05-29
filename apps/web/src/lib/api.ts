/**
 * Typed fetch wrappers for the LedgerCopilot API.
 * Types are derived from the API response shapes — not duplicated by hand
 *.
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface CaseListItem {
  id: string;
  status: string;
  document_type: string | null;
  decision: string | null;
  risk_score: number | null;
  created_at: string;
  original_filename: string;
}

export interface FieldValue {
  value: string | number | null;
  confidence: number;
  source: string;
}

export interface ExtractionFields {
  supplier_name?: FieldValue;
  tax_id_cnpj?: FieldValue;
  total_amount?: FieldValue;
  currency?: FieldValue;
  issue_date?: FieldValue;
  due_date?: FieldValue;
  document_number?: FieldValue;
}

export interface ValidationRule {
  rule: string;
  passed: boolean;
  severity: string;
  detail: string | null;
}

export interface CaseDetail {
  id: string;
  status: string;
  document_type: string | null;
  decision: string | null;
  reason_code: string | null;
  risk_score: number | null;
  justification: string | null;
  trace_id: string;
  pipeline_version: string;
  created_at: string;
  updated_at: string;
  document_id: string;
  original_filename: string;
  file_hash: string;
  channel: string;
  extraction: ExtractionFields | null;
  overall_confidence: number | null;
  validations: ValidationRule[];
  has_blocking_failure: boolean;
}

export interface AuditEvent {
  id: string;
  actor_type: string;
  actor_id: string | null;
  from_status: string;
  to_status: string;
  prompt_version_id: string | null;
  model_name: string | null;
  trace_id: string;
  payload: Record<string, unknown>;
  occurred_at: string;
}

export interface CasesListResponse {
  items: CaseListItem[];
  total: number;
  page: number;
  page_size: number;
}

// Phase 3: prompt versions
export interface PromptVersion {
  id: string;
  alias: string | null;
  name: string;
  description: string;
  is_active: boolean;
  scorecard: Record<string, unknown> | null;
  created_at: string;
}

// Phase 3: monitoring
export interface StageMetric {
  stage: string;
  model: string;
  total_runs: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  total_cost_usd: number;
  avg_input_tokens: number;
  avg_output_tokens: number;
}

export interface CaseThroughput {
  status: string;
  count: number;
}

export interface MonitoringData {
  stage_metrics: StageMetric[];
  case_throughput: CaseThroughput[];
  total_cost_usd: number;
  total_model_runs: number;
}

// Phase 4: executive dashboard types
export interface DecisionBreakdown {
  decision: string | null;
  count: number;
  pct: number;
}

export interface StatusBreakdown {
  status: string;
  count: number;
}

export interface DashboardData {
  total_cases: number;
  cases_this_week: number;
  pending_review: number;
  avg_confidence: number | null;
  total_cost_usd: number;
  avg_cost_per_doc_usd: number;
  decision_breakdown: DecisionBreakdown[];
  status_breakdown: StatusBreakdown[];
}

// Phase 4: email intake
export interface EmailIntakeRequest {
  from_address: string;
  subject: string;
  body_text: string;
  attachments?: string[];
}

export interface EmailIntakeResponse {
  case_id: string;
  document_id: string;
  message: string;
}

async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    cache: "no-store",
    ...opts,
  });
  if (!res.ok) throw new Error(`API error ${res.status} for ${path}`);
  return res.json() as Promise<T>;
}

/** Client-side fetch that attaches the JWT from localStorage. */
export async function apiFetchAuthed<T>(
  path: string,
  opts?: RequestInit,
): Promise<T> {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("lc_token") : null;
  return apiFetch<T>(path, {
    ...opts,
    headers: {
      ...(opts?.headers ?? {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
}

export const api = {
  cases: {
    list: (page = 1) =>
      apiFetch<CasesListResponse>(`/api/v1/cases?page=${page}&page_size=20`),
    get: (id: string) => apiFetch<CaseDetail>(`/api/v1/cases/${id}`),
    audit: (id: string) => apiFetch<AuditEvent[]>(`/api/v1/cases/${id}/audit`),
    auditExportUrl: (id: string) => `${BASE_URL}/api/v1/cases/${id}/audit-export`,
  },
  prompts: {
    list: () => apiFetch<PromptVersion[]>("/api/v1/prompts"),
    get: (id: string) => apiFetch<PromptVersion>(`/api/v1/prompts/${id}`),
  },
  monitoring: {
    get: () => apiFetch<MonitoringData>("/api/v1/monitoring"),
  },
  dashboard: {
    get: () => apiFetch<DashboardData>("/api/v1/dashboard"),
  },
  intake: {
    email: (body: EmailIntakeRequest) =>
      apiFetchAuthed<EmailIntakeResponse>("/api/v1/intake/email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
  },
};
