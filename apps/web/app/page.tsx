"use client";

/**
 * FrankenLedger — Upload / Monster-Lab screen (/)
 *
 * Flow:
 *  idle  →  uploading  →  mapping  →  reconciling  →  /dashboard
 *
 * The four stitched technologies are shown as body parts being stitched.
 * A "Fictional sample data — Noor General Store" banner appears whenever
 * sample data is loaded.
 * The mode badge reads the live agent status and shows
 * "Deterministic mode — parser + rules only, no AI key configured" when
 * no LLM key is set.
 *
 * No credentials, no API key, no secret is ever placed here.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  agentStatus,
  uploadChat,
  uploadLedger,
  uploadSample,
  confirmMapping,
  reconcile,
  type AgentStatus,
  type ChatSummary,
  type LedgerSummary,
  type ReconcileResponse,
  ApiError,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// Canonical mapping fields
// ---------------------------------------------------------------------------
const MAPPING_FIELDS = [
  { key: "date",     label: "Date column" },
  { key: "customer", label: "Customer column" },
  { key: "item",     label: "Item column" },
  { key: "quantity", label: "Quantity column" },
  { key: "amount",   label: "Amount column" },
  { key: "paid",     label: "Paid column" },
] as const;

type MappingKey = (typeof MAPPING_FIELDS)[number]["key"];

// ---------------------------------------------------------------------------
// Body-parts "stitch" display
// ---------------------------------------------------------------------------
const BODY_PARTS = [
  {
    emoji: "🧠",
    tech: "WhatsApp Chat Export",
    label: "Brain — orders from the chat",
    colour: "text-pink-400",
    bg: "bg-pink-950/40",
    border: "border-pink-700/50",
  },
  {
    emoji: "💀",
    tech: "Excel Ledger (.xlsx/.csv)",
    label: "Skeleton — the shop's books",
    colour: "text-yellow-300",
    bg: "bg-yellow-950/40",
    border: "border-yellow-700/50",
  },
  {
    emoji: "⚡",
    tech: "LLM Agent (Gemini / Groq)",
    label: "Spark of life — AI structuring",
    colour: "text-purple-400",
    bg: "bg-purple-950/40",
    border: "border-purple-700/50",
  },
  {
    emoji: "📄",
    tech: "Printable PDF Ledger",
    label: "Paper skin — the daily report",
    colour: "text-green-400",
    bg: "bg-green-950/40",
    border: "border-green-700/50",
  },
] as const;

// ---------------------------------------------------------------------------
// UploadZone component
// ---------------------------------------------------------------------------
interface UploadZoneProps {
  id: string;
  accept: string;
  label: string;
  hint: string;
  icon: string;
  file: File | null;
  summary: ChatSummary | LedgerSummary | null;
  loading: boolean;
  error: string | null;
  onFile: (f: File) => void;
  disabled: boolean;
}

function UploadZone({
  id,
  accept,
  label,
  hint,
  icon,
  file,
  summary,
  loading,
  error,
  onFile,
  disabled,
}: UploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      if (disabled) return;
      const f = e.dataTransfer.files[0];
      if (f) onFile(f);
    },
    [disabled, onFile]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const f = e.target.files?.[0];
      if (f) onFile(f);
    },
    [onFile]
  );

  const ready = !!file && !!summary && !error;

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label={`Upload zone: ${label}`}
      onClick={() => !disabled && inputRef.current?.click()}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); !disabled && inputRef.current?.click(); } }}
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={[
        "relative flex flex-col items-center justify-center gap-3",
        "min-h-[160px] rounded-2xl border-2 border-dashed p-6",
        "transition-all duration-200 cursor-pointer select-none",
        disabled ? "opacity-50 cursor-not-allowed" : "hover:border-red-500/70 hover:bg-red-950/10",
        dragging ? "border-red-500 bg-red-950/20 scale-[1.02]" : "",
        ready ? "border-green-600 bg-green-950/20" : "border-zinc-600 bg-zinc-900/60",
        error ? "border-red-500 bg-red-950/20" : "",
      ].join(" ")}
    >
      <input
        ref={inputRef}
        id={id}
        type="file"
        accept={accept}
        className="sr-only"
        onChange={handleChange}
        disabled={disabled}
        aria-hidden="true"
      />

      {loading ? (
        <div className="flex flex-col items-center gap-2">
          <span className="text-3xl animate-spin">⚙️</span>
          <span className="text-sm text-zinc-400">Uploading…</span>
        </div>
      ) : ready ? (
        <div className="flex flex-col items-center gap-1 text-center">
          <span className="text-3xl">✅</span>
          <span className="text-sm font-semibold text-green-400">{file!.name}</span>
          {"lines" in summary! ? (
            <span className="text-xs text-zinc-400">
              {(summary as ChatSummary).lines} lines · {(summary as ChatSummary).parsed_lines} parsed
            </span>
          ) : (
            <span className="text-xs text-zinc-400">
              {(summary as LedgerSummary).row_count} rows · {(summary as LedgerSummary).columns.length} columns
            </span>
          )}
        </div>
      ) : (
        <div className="flex flex-col items-center gap-2 text-center pointer-events-none">
          <span className="text-4xl">{icon}</span>
          <span className="text-base font-semibold text-zinc-200">{label}</span>
          <span className="text-xs text-zinc-500">{hint}</span>
        </div>
      )}

      {error && (
        <p className="mt-2 text-xs text-red-400 text-center">{error}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mode badge
// ---------------------------------------------------------------------------
function ModeBadge({ status }: { status: AgentStatus | null }) {
  if (!status) return null;

  const isDeterministic = status.mode === "deterministic";

  return (
    <div
      role="status"
      aria-live="polite"
      className={[
        "inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-medium",
        isDeterministic
          ? "bg-zinc-800 text-zinc-300 border border-zinc-600"
          : "bg-purple-900/60 text-purple-300 border border-purple-600",
      ].join(" ")}
    >
      <span className="w-2 h-2 rounded-full inline-block" style={{ background: isDeterministic ? "#71717a" : "#a855f7" }} />
      {isDeterministic
        ? "Deterministic mode — parser + rules only, no AI key configured"
        : `LLM mode — ${status.provider ?? "AI"} (hosted API, no fine-tuning)`}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sample banner
// ---------------------------------------------------------------------------
function SampleBanner() {
  return (
    <div
      role="alert"
      className="flex items-center gap-3 rounded-xl border border-amber-600/60 bg-amber-950/40 px-4 py-3 text-sm text-amber-300"
    >
      <span className="text-lg" aria-hidden="true">🧪</span>
      <span>
        <strong>Fictional sample data — Noor General Store.</strong>{" "}
        All customers, items, and amounts are invented. Not a real shop.
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mapping confirmation step
// ---------------------------------------------------------------------------
interface MappingConfirmProps {
  ledgerSummary: LedgerSummary;
  onConfirm: (mapping: Record<string, string | null>) => void;
  loading: boolean;
}

function MappingConfirm({ ledgerSummary, onConfirm, loading }: MappingConfirmProps) {
  const { suggested_mapping, columns, preview_rows } = ledgerSummary;

  // Initialise local state from suggested mapping
  const [mapping, setMapping] = useState<Record<string, string | null>>(
    () => {
      const m: Record<string, string | null> = {};
      for (const { key } of MAPPING_FIELDS) {
        m[key] = suggested_mapping[key] ?? null;
      }
      return m;
    }
  );

  const colOptions = [null, ...columns];

  return (
    <section aria-labelledby="mapping-heading" className="flex flex-col gap-5">
      <div>
        <h2 id="mapping-heading" className="text-xl font-bold text-zinc-100">
          Step 2 — Confirm Column Mapping
        </h2>
        <p className="mt-1 text-sm text-zinc-400">
          These are the suggested column assignments for your ledger. Adjust any
          that look wrong, then confirm.
        </p>
      </div>

      {/* Mapping selects */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {MAPPING_FIELDS.map(({ key, label }) => (
          <div key={key} className="flex flex-col gap-1">
            <label
              htmlFor={`map-${key}`}
              className="text-xs font-semibold uppercase tracking-wide text-zinc-400"
            >
              {label}
            </label>
            <select
              id={`map-${key}`}
              value={mapping[key] ?? ""}
              onChange={(e) =>
                setMapping((prev) => ({
                  ...prev,
                  [key as MappingKey]: e.target.value || null,
                }))
              }
              disabled={loading}
              className="rounded-lg border border-zinc-600 bg-zinc-800 px-3 py-2.5 text-sm text-zinc-200 focus:outline-none focus:ring-2 focus:ring-red-600 min-h-[44px]"
            >
              <option value="">(not mapped)</option>
              {colOptions.filter(Boolean).map((col) => (
                <option key={col} value={col!}>
                  {col}
                </option>
              ))}
            </select>
          </div>
        ))}
      </div>

      {/* Preview table */}
      {preview_rows.length > 0 && (
        <div>
          <p className="mb-2 text-xs text-zinc-500 uppercase tracking-wide">
            Ledger preview (first {preview_rows.length} rows)
          </p>
          <div className="overflow-x-auto rounded-xl border border-zinc-700 bg-zinc-900/50">
            <table className="w-full text-xs text-left text-zinc-300">
              <thead>
                <tr className="border-b border-zinc-700 bg-zinc-800/60">
                  {columns.map((col) => (
                    <th key={col} className="px-3 py-2 font-semibold text-zinc-400 whitespace-nowrap">
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview_rows.map((row, i) => (
                  <tr key={i} className="border-b border-zinc-800 hover:bg-zinc-800/40">
                    {columns.map((col) => (
                      <td key={col} className="px-3 py-2 whitespace-nowrap text-zinc-300">
                        {row[col] ?? <span className="text-zinc-600">—</span>}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <button
        onClick={() => onConfirm(mapping)}
        disabled={loading}
        className="self-start min-h-[52px] rounded-xl bg-red-700 hover:bg-red-600 disabled:opacity-50 px-8 py-3 text-base font-bold text-white transition-colors focus:outline-none focus:ring-2 focus:ring-red-500"
        aria-busy={loading}
      >
        {loading ? "Analysing…" : "Confirm mapping & analyse →"}
      </button>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------
type Step = "idle" | "uploading" | "mapping" | "reconciling" | "done";

export default function UploadPage() {
  const router = useRouter();

  // Mode badge
  const [agentMode, setAgentMode] = useState<AgentStatus | null>(null);

  // Upload state
  const [chatFile, setChatFile] = useState<File | null>(null);
  const [chatSummary, setChatSummary] = useState<ChatSummary | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  const [chatLoading, setChatLoading] = useState(false);

  const [ledgerFile, setLedgerFile] = useState<File | null>(null);
  const [ledgerSummary, setLedgerSummary] = useState<LedgerSummary | null>(null);
  const [ledgerError, setLedgerError] = useState<string | null>(null);
  const [ledgerLoading, setLedgerLoading] = useState(false);

  const [isSample, setIsSample] = useState(false);
  const [sampleLoading, setSampleLoading] = useState(false);

  const [step, setStep] = useState<Step>("idle");
  const [globalError, setGlobalError] = useState<string | null>(null);

  // Fetch agent status on mount (fire-and-forget — never blocks the UI)
  useEffect(() => {
    agentStatus()
      .then(setAgentMode)
      .catch(() => {
        // Backend might not be running in build-time — that's fine
      });
  }, []);

  // Auto-advance to mapping when both files are ready
  const bothReady = !!chatSummary && !!ledgerSummary;

  useEffect(() => {
    if (bothReady && step === "idle") {
      setStep("mapping");
    }
  }, [bothReady, step]);

  // ---------------------------------------------------------------------------
  // Upload handlers
  // ---------------------------------------------------------------------------
  const handleChatFile = useCallback(async (f: File) => {
    if (!f.name.toLowerCase().endsWith(".txt")) {
      setChatError("Please upload a WhatsApp chat export as a .txt file.");
      return;
    }
    setChatFile(f);
    setChatError(null);
    setChatLoading(true);
    try {
      const summary = await uploadChat(f);
      setChatSummary(summary);
    } catch (e) {
      setChatError(e instanceof ApiError ? e.detail : "Upload failed. Check the file and try again.");
      setChatFile(null);
      setChatSummary(null);
    } finally {
      setChatLoading(false);
    }
  }, []);

  const handleLedgerFile = useCallback(async (f: File) => {
    const ext = f.name.toLowerCase().split(".").pop();
    if (ext !== "xlsx" && ext !== "csv") {
      setLedgerError("Please upload an Excel (.xlsx) or CSV (.csv) file.");
      return;
    }
    setLedgerFile(f);
    setLedgerError(null);
    setLedgerLoading(true);
    try {
      const summary = await uploadLedger(f);
      setLedgerSummary(summary);
    } catch (e) {
      setLedgerError(e instanceof ApiError ? e.detail : "Upload failed. Check the file and try again.");
      setLedgerFile(null);
      setLedgerSummary(null);
    } finally {
      setLedgerLoading(false);
    }
  }, []);

  const handleSample = useCallback(async () => {
    setSampleLoading(true);
    setGlobalError(null);
    setChatError(null);
    setLedgerError(null);
    try {
      const resp = await uploadSample();
      // Create synthetic File stubs so the drop zones show as "ready"
      const chatBlob = new Blob([], { type: "text/plain" });
      const ledgerBlob = new Blob([], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
      setChatFile(new File([chatBlob], "sample-chat-export.txt", { type: "text/plain" }));
      setLedgerFile(new File([ledgerBlob], "sample-ledger.xlsx"));
      setChatSummary(resp.chat);
      setLedgerSummary(resp.ledger);
      setIsSample(true);
      setStep("mapping");
    } catch (e) {
      setGlobalError(
        e instanceof ApiError
          ? `Sample load failed: ${e.detail}`
          : "Could not load sample data. Is the backend running?"
      );
    } finally {
      setSampleLoading(false);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Mapping confirmation + reconcile
  // ---------------------------------------------------------------------------
  const handleConfirmMapping = useCallback(
    async (mapping: Record<string, string | null>) => {
      setStep("reconciling");
      setGlobalError(null);
      try {
        await confirmMapping(mapping);
        const result: ReconcileResponse = await reconcile();
        // Store session data in sessionStorage so /dashboard can read it
        sessionStorage.setItem("fl_reconciled", JSON.stringify(result.reconciled));
        sessionStorage.setItem("fl_flags", JSON.stringify(result.flags));
        sessionStorage.setItem("fl_totals", JSON.stringify(result.totals));
        sessionStorage.setItem("fl_is_sample", JSON.stringify(isSample));
        sessionStorage.setItem("fl_mode", JSON.stringify(agentMode));
        setStep("done");
        router.push("/dashboard");
      } catch (e) {
        setGlobalError(
          e instanceof ApiError
            ? `Analysis failed: ${e.detail}`
            : "Something went wrong during analysis. Is the backend running?"
        );
        setStep("mapping");
      }
    },
    [isSample, agentMode, router]
  );

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  const isLocked = step === "reconciling" || step === "done";

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      {/* ── Header ── */}
      <header className="border-b border-zinc-800 bg-zinc-900/80 px-4 py-4 sm:px-8">
        <div className="mx-auto flex max-w-3xl flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-zinc-100">
              ⚗️ FrankenLedger
            </h1>
            <p className="text-sm text-zinc-500">
              Stitch your WhatsApp books and Excel ledger together.
              <span className="ml-2 italic text-zinc-600">
                No WhatsApp API. No payments. No accounts.
              </span>
            </p>
          </div>
          <ModeBadge status={agentMode} />
        </div>
      </header>

      <div className="mx-auto max-w-3xl px-4 py-8 sm:px-8 flex flex-col gap-8">

        {/* ── Sample banner ── */}
        {isSample && <SampleBanner />}

        {/* ── Global error ── */}
        {globalError && (
          <div role="alert" className="rounded-xl border border-red-600/60 bg-red-950/40 px-4 py-3 text-sm text-red-300">
            <strong>Error: </strong>{globalError}
          </div>
        )}

        {/* ── Step 1: Upload / Monster-Lab ── */}
        {step !== "mapping" && step !== "reconciling" && step !== "done" && (
          <section aria-labelledby="upload-heading" className="flex flex-col gap-6">
            <div>
              <h2 id="upload-heading" className="text-xl font-bold text-zinc-100">
                Step 1 — Upload your files
              </h2>
              <p className="mt-1 text-sm text-zinc-400">
                Export your WhatsApp chat as .txt and upload your Excel or CSV ledger.
                Or load the fictional sample set in one click.
              </p>
            </div>

            {/* ── Four body-parts ── */}
            <div className="rounded-2xl border border-zinc-700/60 bg-zinc-900/40 p-5">
              <p className="mb-4 text-xs font-semibold uppercase tracking-widest text-zinc-500">
                Four technologies being stitched together
              </p>
              <div className="flex flex-col gap-3">
                {BODY_PARTS.map((part, i) => (
                  <div
                    key={i}
                    className={`flex items-center gap-3 rounded-xl border px-4 py-3 ${part.bg} ${part.border}`}
                  >
                    <span className="text-2xl" role="img" aria-label={part.label}>
                      {part.emoji}
                    </span>
                    <div className="flex flex-col">
                      <span className={`text-sm font-semibold ${part.colour}`}>
                        {part.tech}
                      </span>
                      <span className="text-xs text-zinc-500">{part.label}</span>
                    </div>
                    {/* Stitch needle between items */}
                    {i < BODY_PARTS.length - 1 && (
                      <span
                        className="ml-auto text-zinc-600 animate-pulse text-lg"
                        aria-hidden="true"
                        title="stitching"
                      >
                        🪡
                      </span>
                    )}
                  </div>
                ))}
              </div>
              <p className="mt-4 text-xs text-zinc-600 italic">
                My shop&apos;s books live in WhatsApp and Excel. Both are lying to me.
              </p>
            </div>

            {/* ── Drop zones ── */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <UploadZone
                id="chat-upload"
                accept=".txt"
                label="WhatsApp Chat Export"
                hint="Drag & drop or tap • .txt file"
                icon="💬"
                file={chatFile}
                summary={chatSummary}
                loading={chatLoading}
                error={chatError}
                onFile={handleChatFile}
                disabled={isLocked || sampleLoading}
              />
              <UploadZone
                id="ledger-upload"
                accept=".xlsx,.csv"
                label="Shop Ledger"
                hint="Drag & drop or tap • .xlsx or .csv"
                icon="📊"
                file={ledgerFile}
                summary={ledgerSummary}
                loading={ledgerLoading}
                error={ledgerError}
                onFile={handleLedgerFile}
                disabled={isLocked || sampleLoading}
              />
            </div>

            {/* ── Sample button ── */}
            <div className="flex flex-col items-center gap-2">
              <div className="flex items-center gap-4 w-full">
                <div className="flex-1 border-t border-zinc-700" />
                <span className="text-xs text-zinc-600 whitespace-nowrap">or try the sample</span>
                <div className="flex-1 border-t border-zinc-700" />
              </div>
              <button
                onClick={handleSample}
                disabled={isLocked || sampleLoading || chatLoading || ledgerLoading}
                className="min-h-[52px] w-full rounded-xl border border-amber-600/60 bg-amber-950/40 hover:bg-amber-950/60 disabled:opacity-50 px-6 py-3 text-sm font-semibold text-amber-300 transition-colors focus:outline-none focus:ring-2 focus:ring-amber-500"
                aria-busy={sampleLoading}
              >
                {sampleLoading ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="animate-spin">⚙️</span> Loading fictional sample data…
                  </span>
                ) : (
                  "🧪 Load fictional sample — Noor General Store"
                )}
              </button>
              <p className="text-xs text-zinc-600 text-center">
                Fictional data only. No real shop, no real customers.
              </p>
            </div>

            {/* Progress indicator */}
            <div className="flex items-center gap-3 text-sm text-zinc-500" aria-live="polite">
              <span className={chatSummary ? "text-green-400" : "text-zinc-600"}>
                {chatSummary ? "✔" : "○"} Chat export
              </span>
              <span className="text-zinc-700">—</span>
              <span className={ledgerSummary ? "text-green-400" : "text-zinc-600"}>
                {ledgerSummary ? "✔" : "○"} Ledger
              </span>
              <span className="text-zinc-700">—</span>
              <span className="text-zinc-600">○ Mapping</span>
              <span className="text-zinc-700">—</span>
              <span className="text-zinc-600">○ Dashboard</span>
            </div>
          </section>
        )}

        {/* ── Step 2: Mapping confirmation ── */}
        {(step === "mapping" || step === "reconciling") && ledgerSummary && (
          <>
            {/* Show sample banner again in mapping step if applicable */}
            {!isSample && <div />}

            {/* Mini recap */}
            <div className="flex flex-wrap gap-3 text-xs text-zinc-500">
              <span className="text-green-400">✔ Chat: {chatFile?.name ?? "sample"}</span>
              <span className="text-zinc-700">|</span>
              <span className="text-green-400">✔ Ledger: {ledgerFile?.name ?? "sample"}</span>
            </div>

            {/* Progress indicator */}
            <div className="flex items-center gap-3 text-sm text-zinc-500" aria-live="polite">
              <span className="text-green-400">✔ Chat export</span>
              <span className="text-zinc-700">—</span>
              <span className="text-green-400">✔ Ledger</span>
              <span className="text-zinc-700">—</span>
              <span className={step === "mapping" ? "text-amber-400 font-semibold" : "text-green-400"}>
                {step === "reconciling" ? "✔" : "→"} Mapping
              </span>
              <span className="text-zinc-700">—</span>
              <span className={step === "reconciling" ? "text-amber-400 font-semibold animate-pulse" : "text-zinc-600"}>
                {step === "reconciling" ? "⚙ Analysing…" : "○ Dashboard"}
              </span>
            </div>

            <MappingConfirm
              ledgerSummary={ledgerSummary}
              onConfirm={handleConfirmMapping}
              loading={step === "reconciling"}
            />
          </>
        )}

        {/* ── Footer ── */}
        <footer className="border-t border-zinc-800 pt-6 text-xs text-zinc-600 flex flex-col gap-1">
          <p>
            Built with Kiro — FrankenLedger, Kiroween 2026.
          </p>
          <p>
            This app reads a chat export you make yourself. It never touches a live WhatsApp account,
            never sends messages, never reads live chats.
          </p>
          <p>
            No accounts. No database. Nothing stored after your session ends.
          </p>
        </footer>
      </div>
    </main>
  );
}
