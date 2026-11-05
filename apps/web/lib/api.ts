/**
 * FrankenLedger — typed API client for the FastAPI backend.
 *
 * Base URL comes from NEXT_PUBLIC_API_URL (set in .env.local for dev).
 * Default: http://localhost:8000
 *
 * No credentials, no secrets, no auth headers anywhere in this file.
 * All calls are plain JSON / multipart form-data over the public API.
 */

const BASE =
  (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL) ||
  "http://localhost:8000";

// ---------------------------------------------------------------------------
// Shared types (mirrors the FastAPI response shapes)
// ---------------------------------------------------------------------------

export interface ChatSummary {
  lines: number;
  date_range: [string | null, string | null];
  senders: string[];
  parsed_lines: number;
  unparsed_lines: number;
  voice_notes: number;
  preview_lines: string[];
  sample: boolean;
  label: string;
}

export interface LedgerSummary {
  columns: string[];
  row_count: number;
  suggested_mapping: Record<string, string | null>;
  preview_rows: Record<string, string | null>[];
  sample: boolean;
  label: string;
}

export interface SampleResponse {
  sample: boolean;
  label: string;
  chat: ChatSummary;
  ledger: LedgerSummary;
}

export interface ConfirmMappingResponse {
  status: string;
  confirmed_mapping: Record<string, string | null>;
  missing_fields: string[];
  note: string;
}

export interface CandidateOrder {
  date: string | null;
  sender: string | null;
  item: string | null;
  item_raw: string | null;
  quantity: number | null;
  unit: string | null;
  amount_pkr: number | null;
  payment_status: string;
  source_line: number;
  confidence: string;
}

export interface ParseResponse {
  mode: string;
  label: string;
  sample: boolean;
  parsed_lines: number;
  unparsed_lines: number;
  voice_notes: number;
  orders: CandidateOrder[];
  order_count: number;
}

export interface LedgerRow {
  row_index: number;
  date: string | null;
  customer: string | null;
  item: string | null;
  quantity: string | null;
  amount_pkr: number | null;
  paid: boolean | null;
  raw: Record<string, string | null>;
}

export interface Flag {
  flag_id: string;
  kind: string;
  chat_order: CandidateOrder | null;
  ledger_rows: LedgerRow[];
  explanation: string;
  fix_description: string;
  dismissed: boolean;
}

export interface Totals {
  sold: number;
  received: number;
  outstanding: number;
}

export interface ReconcileResponse {
  reconciled: LedgerRow[];
  flags: Flag[];
  totals: Totals;
}

export interface AgentStatus {
  mode: "llm" | "deterministic";
  provider?: string;
  label: string;
}

export interface ExplainResponse {
  explanation: string;
  source: "llm" | "template";
  agent_note?: string;
}

export interface DraftReplyResponse {
  draft: string;
  source: "llm" | "template";
  agent_note?: string;
}

export interface HealthResponse {
  ok: boolean;
  status: string;
  mode: "llm" | "deterministic";
  service: string;
  version: string;
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string
  ) {
    super(`API ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch {
      // ignore JSON parse errors on error responses
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

function url(path: string): string {
  return `${BASE}${path}`;
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export async function health(): Promise<HealthResponse> {
  const res = await fetch(url("/api/health"));
  return handleResponse<HealthResponse>(res);
}

// ---------------------------------------------------------------------------
// Upload
// ---------------------------------------------------------------------------

export async function uploadChat(file: File): Promise<ChatSummary> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(url("/api/upload/chat"), {
    method: "POST",
    body: form,
  });
  return handleResponse<ChatSummary>(res);
}

export async function uploadLedger(file: File): Promise<LedgerSummary> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(url("/api/upload/ledger"), {
    method: "POST",
    body: form,
  });
  return handleResponse<LedgerSummary>(res);
}

export async function uploadSample(): Promise<SampleResponse> {
  const res = await fetch(url("/api/upload/sample"), { method: "POST" });
  return handleResponse<SampleResponse>(res);
}

export async function confirmMapping(
  mapping: Record<string, string | null>
): Promise<ConfirmMappingResponse> {
  const res = await fetch(url("/api/upload/confirm-mapping"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mapping }),
  });
  return handleResponse<ConfirmMappingResponse>(res);
}

// ---------------------------------------------------------------------------
// Parse + Reconcile
// ---------------------------------------------------------------------------

export async function parse(): Promise<ParseResponse> {
  const res = await fetch(url("/api/parse"), { method: "POST" });
  return handleResponse<ParseResponse>(res);
}

export async function reconcile(): Promise<ReconcileResponse> {
  const res = await fetch(url("/api/reconcile"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return handleResponse<ReconcileResponse>(res);
}

export async function reconcileFix(
  flagId: string,
  action: "accept" | "edit" | "dismiss",
  patch?: Record<string, unknown>
): Promise<ReconcileResponse> {
  const res = await fetch(url("/api/reconcile/fix"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ flag_id: flagId, action, patch: patch ?? null }),
  });
  return handleResponse<ReconcileResponse>(res);
}

// ---------------------------------------------------------------------------
// Agent
// ---------------------------------------------------------------------------

export async function agentStatus(): Promise<AgentStatus> {
  const res = await fetch(url("/api/agent/status"));
  return handleResponse<AgentStatus>(res);
}

export async function agentExplain(flag: Flag): Promise<ExplainResponse> {
  const res = await fetch(url("/api/agent/explain"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ flag }),
  });
  return handleResponse<ExplainResponse>(res);
}

export async function agentDraftReply(
  order: CandidateOrder
): Promise<DraftReplyResponse> {
  const res = await fetch(url("/api/agent/draft-reply"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ order }),
  });
  return handleResponse<DraftReplyResponse>(res);
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export interface ExportPdfPayload {
  reconciled: LedgerRow[];
  totals: Totals;
  date?: string;
  flags: Flag[];
  shop_name?: string;
}

export async function exportPdf(payload: ExportPdfPayload): Promise<Blob> {
  const res = await fetch(url("/api/export/pdf"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch {
      // ignore
    }
    throw new ApiError(res.status, detail);
  }
  return res.blob();
}

export interface ExportXlsxPayload {
  reconciled: LedgerRow[];
  flags: Flag[];
}

export async function exportXlsx(payload: ExportXlsxPayload): Promise<Blob> {
  const res = await fetch(url("/api/export/xlsx"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch {
      // ignore
    }
    throw new ApiError(res.status, detail);
  }
  return res.blob();
}

// ---------------------------------------------------------------------------
// Re-export error class so callers can instanceof-check
// ---------------------------------------------------------------------------
export { ApiError };
