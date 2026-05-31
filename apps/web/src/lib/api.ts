/**
 * Typed fetch wrappers for the LedgerCopilot API.
 * Types are derived from API response shapes — not duplicated by hand.
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

export interface LineItem {
  description: string | null;
  quantity: number | null;
  unit_price: number | null;
  line_total: number | null;
  confidence: number;
}

export interface ExtractionFields {
  supplier_name?: FieldValue;
  tax_id_cnpj?: FieldValue;
  total_amount?: FieldValue;
  currency?: FieldValue;
  issue_date?: FieldValue;
  due_date?: FieldValue;
  document_number?: FieldValue;
  cost_center?: FieldValue;
  category?: FieldValue;
  items?: LineItem[];
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
  requires_dual_approval: boolean;
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
  // Per-version generation config. null means "standard default".
  model: string | null;
  temperature: number | null;
  top_p: number | null;
  max_tokens: number | null;
  k: number | null;
  // Changelog — what changed vs the parent version.
  based_on: string | null;
  change_summary: string | null;
  expected_outcome: string | null;
}

/**
 * One metric compared candidate-vs-baseline. Mirrors eval.gate.MetricVerdict on the
 * server — the verdict/thresholds are computed there so the UI never duplicates gate
 * logic (that duplication is what let the old screen gate on supplier_name).
 */
export interface MetricVerdict {
  key: string;
  label: string;
  candidate: number;
  baseline: number | null;
  delta: number | null;
  threshold_label: string;
  gated: boolean;
  passed: boolean;
  severity: "good" | "warning" | "fail";
}

export interface GateVerdict {
  candidate_id: string;
  baseline_id: string | null;
  has_scorecard: boolean;
  passed: boolean;
  metrics: MetricVerdict[];
  violations: string[];
}

export interface CompareResult {
  a: PromptVersion;
  b: PromptVersion;
  baseline: "a" | "b";
  a_has_scorecard: boolean;
  b_has_scorecard: boolean;
  system_text_changed: boolean;
  metrics: MetricVerdict[];
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
  human_override_rate: number;
  human_override_count: number;
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

/**
 * Resolve the JWT in either runtime: client reads localStorage, Server Components
 * read the mirrored cookie via next/headers. This is what lets server-rendered
 * pages (inbox, case detail, dashboard, monitoring) call the auth'd API — without
 * it the server fetch carries no token and the API answers 401.
 */
async function resolveToken(): Promise<string | null> {
  if (typeof window !== "undefined") {
    return localStorage.getItem("lc_token");
  }
  try {
    const { cookies } = await import("next/headers");
    const store = await cookies();
    return store.get("lc_token")?.value ?? null;
  } catch {
    return null;
  }
}

async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const token = await resolveToken();
  const res = await fetch(`${BASE_URL}${path}`, {
    cache: "no-store",
    ...opts,
    headers: {
      ...(opts?.headers ?? {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!res.ok) throw new Error(`API error ${res.status} for ${path}`);
  return res.json() as Promise<T>;
}

/** Back-compat alias: apiFetch now attaches the JWT in both runtimes. */
export async function apiFetchAuthed<T>(
  path: string,
  opts?: RequestInit,
): Promise<T> {
  return apiFetch<T>(path, opts);
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
    gate: (id: string) => apiFetch<GateVerdict>(`/api/v1/prompts/${id}/gate`),
    compare: (a: string, b?: string, baseline: "a" | "b" = "b") => {
      const params = new URLSearchParams({ a, baseline });
      if (b) params.set("b", b);
      return apiFetch<CompareResult>(`/api/v1/prompts/compare?${params.toString()}`);
    },
    promote: (id: string, alias: string) =>
      apiFetch<PromptVersion>(`/api/v1/prompts/${id}/promote`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ alias }),
      }),
    writeScorecard: (id: string, scorecard: Record<string, unknown>) =>
      apiFetch<PromptVersion>(`/api/v1/prompts/${id}/scorecard`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scorecard }),
      }),
    delete: (id: string) =>
      apiFetch<void>(`/api/v1/prompts/${id}`, { method: "DELETE" }),
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
