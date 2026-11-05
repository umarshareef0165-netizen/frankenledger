"use client";

/**
 * FrankenLedger — Dashboard (/dashboard)
 *
 * Reads session state from sessionStorage (fl_* keys written by the upload
 * page after reconcile).  If missing → friendly prompt to upload first.
 *
 * Renders:
 *  • SampleBanner (when fl_is_sample = true)
 *  • ModeBadge    (from fl_mode)
 *  • TotalsBar    (sold / received / outstanding udhaar)
 *  • Search box   (filters LedgerTable + flag list by customer/item)
 *  • LedgerTable  (reconciled rows, highlighted by search)
 *  • Flag list    (FlagCard × N, linked to /flags?id=<flag_id>)
 *  • Export bar   (PDF + XLSX one-click downloads)
 *
 * No credentials, no API key, no secret anywhere in this file.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  reconcileFix,
  exportPdf,
  exportXlsx,
  agentDraftReply,
  type Flag,
  type LedgerRow,
  type Totals,
  type AgentStatus,
  type CandidateOrder,
  ApiError,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// Helpers — sessionStorage I/O
// ---------------------------------------------------------------------------
function readSession(): {
  reconciled: LedgerRow[];
  flags: Flag[];
  totals: Totals;
  isSample: boolean;
  mode: AgentStatus | null;
} | null {
  try {
    const r = sessionStorage.getItem("fl_reconciled");
    const f = sessionStorage.getItem("fl_flags");
    const t = sessionStorage.getItem("fl_totals");
    if (!r || !f || !t) return null;
    return {
      reconciled: JSON.parse(r) as LedgerRow[],
      flags: JSON.parse(f) as Flag[],
      totals: JSON.parse(t) as Totals,
      isSample: JSON.parse(sessionStorage.getItem("fl_is_sample") ?? "false") as boolean,
      mode: JSON.parse(sessionStorage.getItem("fl_mode") ?? "null") as AgentStatus | null,
    };
  } catch {
    return null;
  }
}

function writeSession(reconciled: LedgerRow[], flags: Flag[], totals: Totals): void {
  try {
    sessionStorage.setItem("fl_reconciled", JSON.stringify(reconciled));
    sessionStorage.setItem("fl_flags", JSON.stringify(flags));
    sessionStorage.setItem("fl_totals", JSON.stringify(totals));
  } catch {
    // Storage full or unavailable — silent
  }
}

// ---------------------------------------------------------------------------
// Download helper
// ---------------------------------------------------------------------------
function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// SampleBanner
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
// ModeBadge
// ---------------------------------------------------------------------------
function ModeBadge({ mode }: { mode: AgentStatus | null }) {
  if (!mode) return null;
  const isDet = mode.mode === "deterministic";
  return (
    <div
      role="status"
      className={[
        "inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium",
        isDet
          ? "bg-zinc-800 text-zinc-300 border border-zinc-600"
          : "bg-purple-900/60 text-purple-300 border border-purple-600",
      ].join(" ")}
    >
      <span
        className="w-2 h-2 rounded-full inline-block"
        style={{ background: isDet ? "#71717a" : "#a855f7" }}
      />
      {isDet
        ? "Deterministic mode — parser + rules only, no AI key configured"
        : `LLM mode — ${mode.provider ?? "AI"} (hosted API, no fine-tuning)`}
    </div>
  );
}

// ---------------------------------------------------------------------------
// TotalsBar
// ---------------------------------------------------------------------------
function TotalsBar({ totals }: { totals: Totals }) {
  const fmt = (n: number) => `Rs ${n.toLocaleString("en-PK")}`;
  return (
    <section aria-label="Totals" className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <div className="rounded-2xl border border-zinc-700 bg-zinc-900/60 px-5 py-4 flex flex-col gap-1">
        <span className="text-xs text-zinc-500 uppercase tracking-wide">Total Sold</span>
        <span className="text-2xl font-bold text-zinc-100">{fmt(totals.sold)}</span>
      </div>
      <div className="rounded-2xl border border-zinc-700 bg-zinc-900/60 px-5 py-4 flex flex-col gap-1">
        <span className="text-xs text-zinc-500 uppercase tracking-wide">Received</span>
        <span className="text-2xl font-bold text-green-400">{fmt(totals.received)}</span>
      </div>
      <div className="rounded-2xl border border-zinc-700 bg-zinc-900/60 px-5 py-4 flex flex-col gap-1">
        <span className="text-xs text-zinc-500 uppercase tracking-wide">Outstanding Udhaar</span>
        <span className="text-2xl font-bold text-red-400">{fmt(totals.outstanding)}</span>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// LedgerTable
// ---------------------------------------------------------------------------
function LedgerTable({
  rows,
  query,
  highlightRowIndex,
  rowRefs,
}: {
  rows: LedgerRow[];
  query: string;
  highlightRowIndex: number | null;
  rowRefs: React.MutableRefObject<Map<number, HTMLTableRowElement>>;
}) {
  const q = query.toLowerCase().trim();
  const visible = q
    ? rows.filter(
        (r) =>
          r.customer?.toLowerCase().includes(q) ||
          r.item?.toLowerCase().includes(q)
      )
    : rows;

  if (visible.length === 0) {
    return (
      <p className="text-sm text-zinc-500 py-4 text-center">
        {q ? `No rows matching "${query}"` : "No ledger rows."}
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-zinc-700 bg-zinc-900/50">
      <table className="w-full text-sm text-left text-zinc-300" aria-label="Reconciled ledger">
        <thead>
          <tr className="border-b border-zinc-700 bg-zinc-800/60 text-xs uppercase tracking-wide text-zinc-400">
            <th className="px-3 py-2">#</th>
            <th className="px-3 py-2">Date</th>
            <th className="px-3 py-2">Customer</th>
            <th className="px-3 py-2">Item</th>
            <th className="px-3 py-2">Qty</th>
            <th className="px-3 py-2">Amount</th>
            <th className="px-3 py-2">Paid</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((row) => {
            const isHighlighted = row.row_index === highlightRowIndex;
            return (
              <tr
                key={row.row_index}
                ref={(el) => {
                  if (el) rowRefs.current.set(row.row_index, el);
                  else rowRefs.current.delete(row.row_index);
                }}
                id={`ledger-row-${row.row_index}`}
                className={[
                  "border-b border-zinc-800 transition-colors",
                  isHighlighted ? "evidence-highlight" : "hover:bg-zinc-800/40",
                ].join(" ")}
              >
                <td className="px-3 py-2 text-zinc-500 text-xs">{row.row_index}</td>
                <td className="px-3 py-2 whitespace-nowrap">{row.date ?? <Dash />}</td>
                <td className="px-3 py-2 font-medium">{row.customer ?? <Dash />}</td>
                <td className="px-3 py-2">{row.item ?? <Dash />}</td>
                <td className="px-3 py-2">{row.quantity ?? <Dash />}</td>
                <td className="px-3 py-2 tabular-nums">
                  {row.amount_pkr != null ? `Rs ${row.amount_pkr}` : <Dash />}
                </td>
                <td className="px-3 py-2">
                  {row.paid === true ? (
                    <span className="text-green-400 font-semibold">Yes</span>
                  ) : row.paid === false ? (
                    <span className="text-red-400">No</span>
                  ) : (
                    <Dash />
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Dash() {
  return <span className="text-zinc-600">—</span>;
}

// ---------------------------------------------------------------------------
// KIND_META — colours + labels for flag kinds
// ---------------------------------------------------------------------------
const KIND_META: Record<string, { colour: string; bg: string; border: string; label: string }> = {
  PAID_NOT_RECORDED:  { colour: "text-orange-400", bg: "bg-orange-950/30", border: "border-orange-700/50", label: "Paid — not recorded" },
  RECORDED_NOT_PAID:  { colour: "text-red-400",    bg: "bg-red-950/30",    border: "border-red-700/50",    label: "Recorded — not paid" },
  PRICE_MISMATCH:     { colour: "text-yellow-400", bg: "bg-yellow-950/30", border: "border-yellow-700/50", label: "Price mismatch" },
  UNMATCHED_ORDER:    { colour: "text-blue-400",   bg: "bg-blue-950/30",   border: "border-blue-700/50",   label: "Unmatched chat order" },
  DUPLICATE:          { colour: "text-purple-400", bg: "bg-purple-950/30", border: "border-purple-700/50", label: "Duplicate entry" },
};
function kindMeta(kind: string) {
  return KIND_META[kind] ?? { colour: "text-zinc-400", bg: "bg-zinc-800/30", border: "border-zinc-600/50", label: kind };
}

// ---------------------------------------------------------------------------
// DraftReply
// ---------------------------------------------------------------------------
function DraftReply({ order }: { order: CandidateOrder }) {
  const [draft, setDraft] = useState<string | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const generate = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const resp = await agentDraftReply(order);
      setDraft(resp.draft);
      setSource(resp.source);
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : "Could not generate draft.");
    } finally {
      setLoading(false);
    }
  }, [order]);

  const copy = useCallback(async () => {
    if (!draft) return;
    try {
      await navigator.clipboard.writeText(draft);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API unavailable — fall back to selection
      const el = document.createElement("textarea");
      el.value = draft;
      document.body.appendChild(el);
      el.select();
      document.execCommand("copy");
      document.body.removeChild(el);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [draft]);

  return (
    <div className="mt-3 flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-zinc-400 uppercase tracking-wide">
          Draft WhatsApp reply
        </span>
        {source && (
          <span className="text-xs text-zinc-600 italic">
            ({source === "llm" ? "AI-generated" : "template-based — deterministic"})
          </span>
        )}
      </div>

      {!draft && !loading && (
        <button
          onClick={generate}
          className="min-h-[44px] rounded-lg border border-zinc-600 bg-zinc-800 hover:bg-zinc-700 px-4 py-2 text-sm text-zinc-300 transition-colors focus:outline-none focus:ring-2 focus:ring-zinc-500"
        >
          💬 Generate draft reply
        </button>
      )}

      {loading && (
        <div className="text-sm text-zinc-500 animate-pulse">Generating…</div>
      )}

      {err && <p className="text-xs text-red-400">{err}</p>}

      {draft && (
        <div className="flex flex-col gap-2">
          <div className="rounded-lg border border-zinc-700 bg-zinc-800/60 px-4 py-3 text-sm text-zinc-200 whitespace-pre-wrap">
            {draft}
          </div>
          <div className="flex gap-2">
            <button
              onClick={copy}
              className="min-h-[44px] rounded-lg border border-zinc-600 bg-zinc-800 hover:bg-zinc-700 px-4 py-2 text-sm font-semibold text-zinc-200 transition-colors focus:outline-none focus:ring-2 focus:ring-zinc-500"
              aria-label="Copy draft reply to clipboard"
            >
              {copied ? "✅ Copied!" : "📋 Copy to clipboard"}
            </button>
            <button
              onClick={generate}
              className="min-h-[44px] rounded-lg border border-zinc-700 bg-zinc-900 hover:bg-zinc-800 px-3 py-2 text-xs text-zinc-500 transition-colors"
              aria-label="Regenerate draft reply"
            >
              ↺ Regenerate
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// FlagCard
// ---------------------------------------------------------------------------
interface FlagCardProps {
  flag: Flag;
  onFix: (flagId: string, action: "accept" | "edit" | "dismiss", patch?: Record<string, unknown>) => Promise<void>;
  onScrollToRow: (rowIndex: number) => void;
  onScrollToLine: (lineNumber: number) => void;
  fixing: boolean;
}

function FlagCard({ flag, onFix, onScrollToRow, onScrollToLine, fixing }: FlagCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [editAmount, setEditAmount] = useState<string>("");
  const [editPaid, setEditPaid] = useState<string>("");
  const meta = kindMeta(flag.kind);

  if (flag.dismissed) {
    return (
      <div className={`rounded-2xl border ${meta.border} bg-zinc-900/30 px-4 py-3 opacity-50`}>
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          <span className="line-through">{meta.label}</span>
          <span>— dismissed</span>
        </div>
      </div>
    );
  }

  return (
    <article
      className={`rounded-2xl border ${meta.border} ${meta.bg} flex flex-col gap-0 overflow-hidden`}
      aria-label={`Flag: ${meta.label}`}
    >
      {/* Header row */}
      <button
        className="flex items-center gap-3 px-4 py-4 text-left w-full focus:outline-none focus:ring-2 focus:ring-inset focus:ring-zinc-500 min-h-[56px]"
        onClick={() => setExpanded((p) => !p)}
        aria-expanded={expanded}
      >
        <span className={`text-xs font-bold uppercase tracking-wider ${meta.colour}`}>
          {meta.label}
        </span>
        <span className="flex-1 text-xs text-zinc-400 line-clamp-1">{flag.explanation}</span>
        <span className="text-zinc-500 text-xs">{expanded ? "▲" : "▼"}</span>
      </button>

      {expanded && (
        <div className="flex flex-col gap-3 px-4 pb-4 border-t border-white/5 pt-3">
          {/* Explanation */}
          <p className="text-sm text-zinc-300">{flag.explanation}</p>

          {/* Evidence */}
          <div className="flex flex-wrap gap-2">
            {flag.chat_order && (
              <button
                onClick={() => onScrollToLine(flag.chat_order!.source_line)}
                className="min-h-[36px] rounded-lg border border-blue-700/50 bg-blue-950/30 px-3 py-1.5 text-xs text-blue-300 hover:bg-blue-900/40 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500"
                title="Click to highlight chat evidence"
              >
                💬 Chat line {flag.chat_order.source_line}
                {flag.chat_order.sender ? ` — ${flag.chat_order.sender}` : ""}
                {flag.chat_order.item ? `, ${flag.chat_order.item}` : ""}
                {flag.chat_order.amount_pkr != null ? ` Rs ${flag.chat_order.amount_pkr}` : ""}
              </button>
            )}
            {flag.ledger_rows.map((lr) => (
              <button
                key={lr.row_index}
                onClick={() => onScrollToRow(lr.row_index)}
                className="min-h-[36px] rounded-lg border border-green-700/50 bg-green-950/30 px-3 py-1.5 text-xs text-green-300 hover:bg-green-900/40 transition-colors focus:outline-none focus:ring-2 focus:ring-green-500"
                title="Click to highlight ledger row"
              >
                📊 Ledger row {lr.row_index}
                {lr.customer ? ` — ${lr.customer}` : ""}
                {lr.item ? `, ${lr.item}` : ""}
                {lr.amount_pkr != null ? ` Rs ${lr.amount_pkr}` : ""}
              </button>
            ))}
          </div>

          {/* Fix description */}
          {flag.fix_description && (
            <p className="text-xs text-zinc-500 italic">{flag.fix_description}</p>
          )}

          {/* Edit form */}
          {editMode && (
            <div className="flex flex-col gap-3 rounded-xl border border-yellow-700/40 bg-yellow-950/20 p-3">
              <p className="text-xs font-semibold text-yellow-400">Edit values</p>
              <div className="flex flex-wrap gap-3">
                <label className="flex flex-col gap-1 text-xs text-zinc-400">
                  Amount (Rs)
                  <input
                    type="number"
                    value={editAmount}
                    onChange={(e) => setEditAmount(e.target.value)}
                    placeholder="e.g. 500"
                    className="min-h-[44px] rounded-lg border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 w-32 focus:outline-none focus:ring-2 focus:ring-yellow-500"
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs text-zinc-400">
                  Paid
                  <select
                    value={editPaid}
                    onChange={(e) => setEditPaid(e.target.value)}
                    className="min-h-[44px] rounded-lg border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:ring-2 focus:ring-yellow-500"
                  >
                    <option value="">(unchanged)</option>
                    <option value="true">Yes</option>
                    <option value="false">No</option>
                  </select>
                </label>
              </div>
              <div className="flex gap-2">
                <button
                  disabled={fixing}
                  onClick={() => {
                    const patch: Record<string, unknown> = {};
                    if (editAmount.trim()) patch.amount_pkr = parseFloat(editAmount);
                    if (editPaid === "true") patch.paid = true;
                    if (editPaid === "false") patch.paid = false;
                    onFix(flag.flag_id, "edit", Object.keys(patch).length ? patch : undefined);
                    setEditMode(false);
                  }}
                  className="min-h-[44px] rounded-lg bg-yellow-700 hover:bg-yellow-600 disabled:opacity-50 px-4 py-2 text-sm font-semibold text-white transition-colors focus:outline-none focus:ring-2 focus:ring-yellow-500"
                >
                  {fixing ? "Saving…" : "Save edit"}
                </button>
                <button
                  onClick={() => setEditMode(false)}
                  className="min-h-[44px] rounded-lg border border-zinc-600 px-4 py-2 text-sm text-zinc-400 hover:bg-zinc-800 transition-colors focus:outline-none focus:ring-2 focus:ring-zinc-500"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Action buttons */}
          {!editMode && (
            <div className="flex flex-wrap gap-2 pt-1">
              <button
                disabled={fixing}
                onClick={() => onFix(flag.flag_id, "accept")}
                className="min-h-[44px] rounded-lg bg-green-800 hover:bg-green-700 disabled:opacity-50 px-5 py-2 text-sm font-semibold text-white transition-colors focus:outline-none focus:ring-2 focus:ring-green-500"
                aria-label={`Accept flag ${flag.flag_id}`}
              >
                {fixing ? "…" : "✔ Accept"}
              </button>
              <button
                disabled={fixing}
                onClick={() => { setEditMode(true); setEditAmount(""); setEditPaid(""); }}
                className="min-h-[44px] rounded-lg bg-yellow-800 hover:bg-yellow-700 disabled:opacity-50 px-5 py-2 text-sm font-semibold text-white transition-colors focus:outline-none focus:ring-2 focus:ring-yellow-500"
                aria-label={`Edit flag ${flag.flag_id}`}
              >
                ✏️ Edit
              </button>
              <button
                disabled={fixing}
                onClick={() => onFix(flag.flag_id, "dismiss")}
                className="min-h-[44px] rounded-lg border border-zinc-600 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 px-5 py-2 text-sm text-zinc-400 transition-colors focus:outline-none focus:ring-2 focus:ring-zinc-500"
                aria-label={`Dismiss flag ${flag.flag_id}`}
              >
                ✕ Dismiss
              </button>
            </div>
          )}

          {/* Draft reply — only for flags that have a chat order with an unpaid item */}
          {flag.chat_order && flag.chat_order.payment_status !== "paid" && (
            <DraftReply order={flag.chat_order} />
          )}
        </div>
      )}
    </article>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------
function EmptyState() {
  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col items-center justify-center gap-6 px-4">
      <div className="text-center flex flex-col gap-3 max-w-sm">
        <span className="text-6xl">⚗️</span>
        <h1 className="text-2xl font-bold text-zinc-100">No session data</h1>
        <p className="text-sm text-zinc-400">
          Upload your files and run the analysis first, then come back here.
        </p>
        <Link
          href="/"
          className="mt-2 inline-block min-h-[52px] rounded-xl bg-red-700 hover:bg-red-600 px-8 py-3 text-base font-bold text-white transition-colors focus:outline-none focus:ring-2 focus:ring-red-500 leading-none flex items-center justify-center"
        >
          ← Upload files
        </Link>
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Main dashboard component
// ---------------------------------------------------------------------------
export default function DashboardPage() {
  // Session state
  const [reconciled, setReconciled] = useState<LedgerRow[] | null>(null);
  const [flags, setFlags] = useState<Flag[] | null>(null);
  const [totals, setTotals] = useState<Totals | null>(null);
  const [isSample, setIsSample] = useState(false);
  const [agentMode, setAgentMode] = useState<AgentStatus | null>(null);
  const [loaded, setLoaded] = useState(false);

  // UI state
  const [search, setSearch] = useState("");
  const [highlightRowIndex, setHighlightRowIndex] = useState<number | null>(null);
  const [fixingId, setFixingId] = useState<string | null>(null);
  const [exportErr, setExportErr] = useState<string | null>(null);
  const [exportingPdf, setExportingPdf] = useState(false);
  const [exportingXlsx, setExportingXlsx] = useState(false);

  const ledgerTableRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<Map<number, HTMLTableRowElement>>(new Map());

  // Load from sessionStorage on mount (client-only)
  useEffect(() => {
    const session = readSession();
    if (session) {
      setReconciled(session.reconciled);
      setFlags(session.flags);
      setTotals(session.totals);
      setIsSample(session.isSample);
      setAgentMode(session.mode);
    }
    setLoaded(true);
  }, []);

  // Scroll-to + highlight ledger row
  const scrollToRow = useCallback((rowIndex: number) => {
    setHighlightRowIndex(rowIndex);
    // Small delay so state renders first
    setTimeout(() => {
      const el = rowRefs.current.get(rowIndex);
      if (el) {
        ledgerTableRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 50);
    // Remove highlight after animation
    setTimeout(() => setHighlightRowIndex(null), 2000);
  }, []);

  // Scroll-to chat line — we can only show it as a toast since we don't
  // render the raw chat text on this page
  const [chatLineToast, setChatLineToast] = useState<string | null>(null);
  const scrollToLine = useCallback((lineNumber: number) => {
    setChatLineToast(`Chat line ${lineNumber} — open your original chat export to see it.`);
    setTimeout(() => setChatLineToast(null), 4000);
  }, []);

  // Fix handler
  const handleFix = useCallback(
    async (flagId: string, action: "accept" | "edit" | "dismiss", patch?: Record<string, unknown>) => {
      setFixingId(flagId);
      try {
        const result = await reconcileFix(flagId, action, patch);
        setReconciled(result.reconciled);
        setFlags(result.flags);
        setTotals(result.totals);
        writeSession(result.reconciled, result.flags, result.totals);
      } catch (e) {
        setExportErr(e instanceof ApiError ? e.detail : "Fix failed. Try again.");
      } finally {
        setFixingId(null);
      }
    },
    []
  );

  // Export PDF
  const handleExportPdf = useCallback(async () => {
    if (!reconciled || !totals || !flags) return;
    setExportingPdf(true);
    setExportErr(null);
    try {
      const blob = await exportPdf({ reconciled, totals, flags });
      const date = new Date().toISOString().slice(0, 10);
      triggerDownload(blob, `frankenledger-${date}.pdf`);
    } catch (e) {
      setExportErr(e instanceof ApiError ? e.detail : "PDF export failed.");
    } finally {
      setExportingPdf(false);
    }
  }, [reconciled, totals, flags]);

  // Export XLSX
  const handleExportXlsx = useCallback(async () => {
    if (!reconciled || !flags) return;
    setExportingXlsx(true);
    setExportErr(null);
    try {
      const blob = await exportXlsx({ reconciled, flags });
      triggerDownload(blob, "frankenledger-ledger.xlsx");
    } catch (e) {
      setExportErr(e instanceof ApiError ? e.detail : "XLSX export failed.");
    } finally {
      setExportingXlsx(false);
    }
  }, [reconciled, flags]);

  // Wait for client-side load before deciding to show empty state
  if (!loaded) {
    return (
      <main className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <span className="text-zinc-500 text-sm animate-pulse">Loading…</span>
      </main>
    );
  }

  if (!reconciled || !flags || !totals) {
    return <EmptyState />;
  }

  const activeFlags = flags.filter((f) => !f.dismissed);
  const q = search.toLowerCase().trim();
  const filteredFlags = q
    ? flags.filter((f) => {
        const co = f.chat_order;
        return (
          co?.sender?.toLowerCase().includes(q) ||
          co?.item?.toLowerCase().includes(q) ||
          f.ledger_rows.some(
            (r) =>
              r.customer?.toLowerCase().includes(q) ||
              r.item?.toLowerCase().includes(q)
          )
        );
      })
    : flags;

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">

      {/* ── Header ── */}
      <header className="sticky top-0 z-10 border-b border-zinc-800 bg-zinc-900/95 backdrop-blur px-4 py-3 sm:px-8">
        <div className="mx-auto max-w-4xl flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <Link href="/" className="text-zinc-500 hover:text-zinc-300 text-sm transition-colors" aria-label="Back to upload">
              ← Upload
            </Link>
            <h1 className="text-xl font-extrabold text-zinc-100">⚗️ FrankenLedger — Dashboard</h1>
          </div>
          <ModeBadge mode={agentMode} />
        </div>
      </header>

      <div className="mx-auto max-w-4xl px-4 py-6 sm:px-8 flex flex-col gap-7">

        {/* ── Sample banner ── */}
        {isSample && <SampleBanner />}

        {/* ── Chat line toast ── */}
        {chatLineToast && (
          <div
            role="status"
            aria-live="polite"
            className="rounded-xl border border-blue-700/50 bg-blue-950/40 px-4 py-3 text-sm text-blue-300"
          >
            💬 {chatLineToast}
          </div>
        )}

        {/* ── Export error ── */}
        {exportErr && (
          <div role="alert" className="rounded-xl border border-red-600/50 bg-red-950/30 px-4 py-3 text-sm text-red-300">
            {exportErr}
          </div>
        )}

        {/* ── Totals ── */}
        <TotalsBar totals={totals} />

        {/* ── Search ── */}
        <div className="flex flex-col gap-2">
          <label htmlFor="search" className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Search by customer or item
          </label>
          <input
            id="search"
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="e.g. Ahmed, cheeni…"
            className="min-h-[48px] rounded-xl border border-zinc-600 bg-zinc-800 px-4 py-2.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-red-600 w-full sm:max-w-sm"
            aria-label="Search ledger and flags"
          />
        </div>

        {/* ── Ledger table ── */}
        <section aria-labelledby="ledger-heading">
          <div className="flex items-center justify-between mb-3">
            <h2 id="ledger-heading" className="text-base font-bold text-zinc-200">
              Reconciled Ledger
              <span className="ml-2 text-xs font-normal text-zinc-500">
                ({reconciled.length} rows)
              </span>
            </h2>
          </div>
          <div ref={ledgerTableRef}>
            <LedgerTable
              rows={reconciled}
              query={search}
              highlightRowIndex={highlightRowIndex}
              rowRefs={rowRefs}
            />
          </div>
        </section>

        {/* ── Flags ── */}
        <section aria-labelledby="flags-heading">
          <div className="flex items-center justify-between mb-3">
            <h2 id="flags-heading" className="text-base font-bold text-zinc-200">
              Flags
              <span className="ml-2 text-xs font-normal text-zinc-500">
                ({activeFlags.length} open
                {flags.length !== activeFlags.length
                  ? `, ${flags.length - activeFlags.length} dismissed`
                  : ""}
                )
              </span>
            </h2>
            {activeFlags.length === 0 && (
              <span className="text-xs text-green-400">✔ All flags resolved</span>
            )}
          </div>

          {filteredFlags.length === 0 ? (
            <p className="text-sm text-zinc-500 py-4 text-center">
              {search ? `No flags matching "${search}"` : "No flags."}
            </p>
          ) : (
            <div className="flex flex-col gap-3">
              {filteredFlags.map((flag) => (
                <FlagCard
                  key={flag.flag_id}
                  flag={flag}
                  onFix={handleFix}
                  onScrollToRow={scrollToRow}
                  onScrollToLine={scrollToLine}
                  fixing={fixingId === flag.flag_id}
                />
              ))}
            </div>
          )}
        </section>

        {/* ── Export bar ── */}
        <section aria-label="Export" className="flex flex-col gap-3 pt-2">
          <h2 className="text-base font-bold text-zinc-200">Export</h2>
          <div className="flex flex-wrap gap-3">
            <button
              onClick={handleExportPdf}
              disabled={exportingPdf}
              className="min-h-[52px] rounded-xl bg-red-800 hover:bg-red-700 disabled:opacity-50 px-6 py-3 text-sm font-bold text-white transition-colors focus:outline-none focus:ring-2 focus:ring-red-500"
              aria-busy={exportingPdf}
            >
              {exportingPdf ? "⚙️ Generating…" : "📄 Download daily PDF"}
            </button>
            <button
              onClick={handleExportXlsx}
              disabled={exportingXlsx}
              className="min-h-[52px] rounded-xl bg-green-800 hover:bg-green-700 disabled:opacity-50 px-6 py-3 text-sm font-bold text-white transition-colors focus:outline-none focus:ring-2 focus:ring-green-500"
              aria-busy={exportingXlsx}
            >
              {exportingXlsx ? "⚙️ Generating…" : "📊 Download clean XLSX"}
            </button>
          </div>
          <p className="text-xs text-zinc-600">
            Your original uploaded file is never overwritten — these are fresh downloads.
          </p>
        </section>

        {/* ── Footer ── */}
        <footer className="border-t border-zinc-800 pt-6 text-xs text-zinc-600 flex flex-col gap-1">
          <p>Built with Kiro — FrankenLedger, Kiroween 2026.</p>
          <p>No WhatsApp API. No payments. No accounts. Nothing stored after your session.</p>
          {isSample && (
            <p className="text-amber-700">
              Sample data shown is fictional — Noor General Store does not exist.
            </p>
          )}
        </footer>
      </div>
    </main>
  );
}
