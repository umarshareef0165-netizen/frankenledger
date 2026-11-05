"use client";

/**
 * FrankenLedger — Flag detail page (/flags)
 *
 * Reads the same fl_* sessionStorage keys written by the upload page.
 * If missing → friendly "upload first" state with a link to /.
 *
 * Each flag card shows:
 *  • Kind badge + explanation
 *  • Evidence section:
 *      – chat line number (click → scrolls to / highlights #chat-line-<N> in
 *        the inline chat-evidence panel, or shows a toast if not rendered)
 *      – ledger row number (click → scrolls to / highlights #flag-ledger-row-<N>)
 *  • Accept / Edit / Dismiss buttons wired to reconcileFix(); totals recompute
 *  • DraftReply (agentDraftReply() + one-click copy-to-clipboard)
 *
 * Phone layout: single column, all tap targets min-h-[44px]+.
 *
 * No credentials, no API key, no secret anywhere in this file.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  reconcileFix,
  agentDraftReply,
  type Flag,
  type LedgerRow,
  type Totals,
  type AgentStatus,
  type CandidateOrder,
  ApiError,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// sessionStorage helpers (same contract as dashboard)
// ---------------------------------------------------------------------------

interface Session {
  reconciled: LedgerRow[];
  flags: Flag[];
  totals: Totals;
  isSample: boolean;
  mode: AgentStatus | null;
}

function readSession(): Session | null {
  try {
    const r = sessionStorage.getItem("fl_reconciled");
    const f = sessionStorage.getItem("fl_flags");
    const t = sessionStorage.getItem("fl_totals");
    if (!r || !f || !t) return null;
    return {
      reconciled: JSON.parse(r) as LedgerRow[],
      flags: JSON.parse(f) as Flag[],
      totals: JSON.parse(t) as Totals,
      isSample: JSON.parse(
        sessionStorage.getItem("fl_is_sample") ?? "false"
      ) as boolean,
      mode: JSON.parse(
        sessionStorage.getItem("fl_mode") ?? "null"
      ) as AgentStatus | null,
    };
  } catch {
    return null;
  }
}

function writeSession(
  reconciled: LedgerRow[],
  flags: Flag[],
  totals: Totals
): void {
  try {
    sessionStorage.setItem("fl_reconciled", JSON.stringify(reconciled));
    sessionStorage.setItem("fl_flags", JSON.stringify(flags));
    sessionStorage.setItem("fl_totals", JSON.stringify(totals));
  } catch {
    // Storage full or unavailable — silent
  }
}

// ---------------------------------------------------------------------------
// KIND_META
// ---------------------------------------------------------------------------
const KIND_META: Record<
  string,
  { colour: string; bg: string; border: string; label: string }
> = {
  PAID_NOT_RECORDED: {
    colour: "text-orange-400",
    bg: "bg-orange-950/30",
    border: "border-orange-700/50",
    label: "Paid — not recorded",
  },
  RECORDED_NOT_PAID: {
    colour: "text-red-400",
    bg: "bg-red-950/30",
    border: "border-red-700/50",
    label: "Recorded — not paid",
  },
  PRICE_MISMATCH: {
    colour: "text-yellow-400",
    bg: "bg-yellow-950/30",
    border: "border-yellow-700/50",
    label: "Price mismatch",
  },
  UNMATCHED_ORDER: {
    colour: "text-blue-400",
    bg: "bg-blue-950/30",
    border: "border-blue-700/50",
    label: "Unmatched chat order",
  },
  DUPLICATE: {
    colour: "text-purple-400",
    bg: "bg-purple-950/30",
    border: "border-purple-700/50",
    label: "Duplicate entry",
  },
};
function kindMeta(kind: string) {
  return (
    KIND_META[kind] ?? {
      colour: "text-zinc-400",
      bg: "bg-zinc-800/30",
      border: "border-zinc-600/50",
      label: kind,
    }
  );
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
      <span className="text-lg" aria-hidden="true">
        🧪
      </span>
      <span>
        <strong>Fictional sample data — Noor General Store.</strong> All
        customers, items, and amounts are invented. Not a real shop.
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
// TotalsBar (compact)
// ---------------------------------------------------------------------------
function TotalsBar({ totals }: { totals: Totals }) {
  const fmt = (n: number) => `Rs ${n.toLocaleString("en-PK")}`;
  return (
    <div className="flex flex-wrap gap-3 rounded-2xl border border-zinc-700 bg-zinc-900/50 px-5 py-4">
      <div className="flex flex-col gap-0.5 min-w-[100px]">
        <span className="text-xs text-zinc-500 uppercase tracking-wide">Sold</span>
        <span className="text-lg font-bold text-zinc-100">{fmt(totals.sold)}</span>
      </div>
      <div className="flex flex-col gap-0.5 min-w-[100px]">
        <span className="text-xs text-zinc-500 uppercase tracking-wide">Received</span>
        <span className="text-lg font-bold text-green-400">{fmt(totals.received)}</span>
      </div>
      <div className="flex flex-col gap-0.5 min-w-[120px]">
        <span className="text-xs text-zinc-500 uppercase tracking-wide">Outstanding</span>
        <span className="text-lg font-bold text-red-400">{fmt(totals.outstanding)}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// LedgerEvidenceRow — inline highlighted ledger row inside a flag card
// ---------------------------------------------------------------------------
function LedgerEvidenceRow({
  row,
  highlighted,
  rowRef,
}: {
  row: LedgerRow;
  highlighted: boolean;
  rowRef: (el: HTMLTableRowElement | null) => void;
}) {
  return (
    <tr
      ref={rowRef}
      id={`flag-ledger-row-${row.row_index}`}
      className={[
        "border-b border-zinc-800 text-xs transition-colors",
        highlighted ? "evidence-highlight" : "",
      ].join(" ")}
    >
      <td className="px-2 py-1.5 text-zinc-500">{row.row_index}</td>
      <td className="px-2 py-1.5 whitespace-nowrap">{row.date ?? "—"}</td>
      <td className="px-2 py-1.5 font-medium">{row.customer ?? "—"}</td>
      <td className="px-2 py-1.5">{row.item ?? "—"}</td>
      <td className="px-2 py-1.5">{row.quantity ?? "—"}</td>
      <td className="px-2 py-1.5 tabular-nums">
        {row.amount_pkr != null ? `Rs ${row.amount_pkr}` : "—"}
      </td>
      <td className="px-2 py-1.5">
        {row.paid === true ? (
          <span className="text-green-400 font-semibold">Yes</span>
        ) : row.paid === false ? (
          <span className="text-red-400">No</span>
        ) : (
          "—"
        )}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// DraftReply — generate + copy-to-clipboard
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
      setErr(
        e instanceof ApiError ? e.detail : "Could not generate draft reply."
      );
    } finally {
      setLoading(false);
    }
  }, [order]);

  const copy = useCallback(async () => {
    if (!draft) return;
    try {
      await navigator.clipboard.writeText(draft);
    } catch {
      // Clipboard API unavailable — execCommand fallback
      const ta = document.createElement("textarea");
      ta.value = draft;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      try {
        document.execCommand("copy");
      } catch {
        // last-resort: nothing we can do silently
      }
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [draft]);

  return (
    <section
      aria-label="Draft WhatsApp reply"
      className="mt-4 flex flex-col gap-2 rounded-xl border border-zinc-700/60 bg-zinc-900/40 p-4"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-zinc-400">
          Draft WhatsApp reply
        </span>
        {source && (
          <span className="text-xs italic text-zinc-600">
            (
            {source === "llm"
              ? "AI-generated"
              : "template-based — deterministic"}
            )
          </span>
        )}
      </div>

      {!draft && !loading && (
        <button
          onClick={generate}
          className="min-h-[44px] self-start rounded-lg border border-zinc-600 bg-zinc-800 px-4 py-2 text-sm text-zinc-300 transition-colors hover:bg-zinc-700 focus:outline-none focus:ring-2 focus:ring-zinc-500"
        >
          💬 Generate draft reply
        </button>
      )}

      {loading && (
        <p className="animate-pulse text-sm text-zinc-500">Generating…</p>
      )}

      {err && <p className="text-xs text-red-400">{err}</p>}

      {draft && (
        <div className="flex flex-col gap-3">
          <div className="rounded-lg border border-zinc-700 bg-zinc-800/60 px-4 py-3 text-sm text-zinc-200 whitespace-pre-wrap leading-relaxed">
            {draft}
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={copy}
              aria-label="Copy draft reply to clipboard"
              className="min-h-[44px] rounded-lg border border-zinc-600 bg-zinc-800 px-5 py-2 text-sm font-semibold text-zinc-200 transition-colors hover:bg-zinc-700 focus:outline-none focus:ring-2 focus:ring-zinc-500"
            >
              {copied ? "✅ Copied!" : "📋 Copy to clipboard"}
            </button>
            <button
              onClick={generate}
              aria-label="Regenerate draft reply"
              className="min-h-[44px] rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-xs text-zinc-500 transition-colors hover:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-500"
            >
              ↺ Regenerate
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// FlagDetail — one full flag card
// ---------------------------------------------------------------------------
interface FlagDetailProps {
  flag: Flag;
  onFix: (
    flagId: string,
    action: "accept" | "edit" | "dismiss",
    patch?: Record<string, unknown>
  ) => Promise<void>;
  fixing: boolean;
}

function FlagDetail({ flag, onFix, fixing }: FlagDetailProps) {
  const meta = kindMeta(flag.kind);
  const [editMode, setEditMode] = useState(false);
  const [editAmount, setEditAmount] = useState("");
  const [editPaid, setEditPaid] = useState("");

  // Per-ledger-row highlight state
  const [highlightedRowIndex, setHighlightedRowIndex] = useState<number | null>(
    null
  );
  const ledgerRowRefs = useRef<Map<number, HTMLTableRowElement>>(new Map());

  // Per-chat-line highlight state
  const [highlightedLineId, setHighlightedLineId] = useState<number | null>(
    null
  );
  const chatLineRefs = useRef<Map<number, HTMLElement>>(new Map());

  const scrollToLedgerRow = useCallback((rowIndex: number) => {
    setHighlightedRowIndex(rowIndex);
    setTimeout(() => {
      const el = ledgerRowRefs.current.get(rowIndex);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 40);
    setTimeout(() => setHighlightedRowIndex(null), 2000);
  }, []);

  const scrollToChatLine = useCallback((lineNumber: number) => {
    setHighlightedLineId(lineNumber);
    setTimeout(() => {
      const el = chatLineRefs.current.get(lineNumber);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 40);
    setTimeout(() => setHighlightedLineId(null), 2000);
  }, []);

  const hasChatOrder = !!flag.chat_order;
  const hasLedgerRows = flag.ledger_rows.length > 0;

  if (flag.dismissed) {
    return (
      <article
        aria-label={`Dismissed flag: ${meta.label}`}
        className={`rounded-2xl border ${meta.border} bg-zinc-900/20 px-5 py-4 opacity-50`}
      >
        <div className="flex items-center gap-3">
          <span
            className={`text-xs font-bold uppercase tracking-wider ${meta.colour} line-through`}
          >
            {meta.label}
          </span>
          <span className="text-xs text-zinc-500">— dismissed</span>
        </div>
      </article>
    );
  }

  return (
    <article
      id={`flag-${flag.flag_id}`}
      aria-labelledby={`flag-heading-${flag.flag_id}`}
      className={`rounded-2xl border ${meta.border} ${meta.bg} flex flex-col gap-0 overflow-hidden`}
    >
      {/* ── Header ── */}
      <div className="flex flex-wrap items-center gap-3 px-5 py-4 border-b border-white/5">
        <span
          id={`flag-heading-${flag.flag_id}`}
          className={`text-sm font-bold uppercase tracking-wider ${meta.colour}`}
        >
          {meta.label}
        </span>
      </div>

      <div className="flex flex-col gap-5 px-5 py-5">
        {/* ── Explanation ── */}
        <p className="text-sm text-zinc-300 leading-relaxed">{flag.explanation}</p>

        {/* ── Evidence chips ── */}
        <div className="flex flex-col gap-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Evidence
          </h3>
          <div className="flex flex-wrap gap-2">
            {hasChatOrder && (
              <button
                onClick={() => scrollToChatLine(flag.chat_order!.source_line)}
                className="min-h-[44px] rounded-xl border border-blue-700/50 bg-blue-950/30 px-4 py-2 text-left text-xs text-blue-300 transition-colors hover:bg-blue-900/40 focus:outline-none focus:ring-2 focus:ring-blue-500"
                title="Click to highlight this chat line below"
                aria-label={`Scroll to chat line ${flag.chat_order!.source_line}`}
              >
                <span className="font-semibold">💬 Chat line {flag.chat_order!.source_line}</span>
                {flag.chat_order!.sender && (
                  <span className="ml-1 text-blue-400/70">
                    — {flag.chat_order!.sender}
                  </span>
                )}
                {flag.chat_order!.item && (
                  <span className="ml-1">{flag.chat_order!.item}</span>
                )}
                {flag.chat_order!.amount_pkr != null && (
                  <span className="ml-1">Rs {flag.chat_order!.amount_pkr}</span>
                )}
              </button>
            )}
            {flag.ledger_rows.map((lr) => (
              <button
                key={lr.row_index}
                onClick={() => scrollToLedgerRow(lr.row_index)}
                className="min-h-[44px] rounded-xl border border-green-700/50 bg-green-950/30 px-4 py-2 text-left text-xs text-green-300 transition-colors hover:bg-green-900/40 focus:outline-none focus:ring-2 focus:ring-green-500"
                title="Click to highlight this ledger row below"
                aria-label={`Scroll to ledger row ${lr.row_index}`}
              >
                <span className="font-semibold">📊 Ledger row {lr.row_index}</span>
                {lr.customer && (
                  <span className="ml-1 text-green-400/70">— {lr.customer}</span>
                )}
                {lr.item && <span className="ml-1">{lr.item}</span>}
                {lr.amount_pkr != null && (
                  <span className="ml-1">Rs {lr.amount_pkr}</span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* ── Chat order detail panel ── */}
        {hasChatOrder && (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Chat order detail
            </h3>
            <div
              id={`chat-line-${flag.chat_order!.source_line}`}
              ref={(el) => {
                if (el)
                  chatLineRefs.current.set(flag.chat_order!.source_line, el);
                else chatLineRefs.current.delete(flag.chat_order!.source_line);
              }}
              className={[
                "rounded-xl border border-blue-700/40 bg-blue-950/20 p-4 text-xs transition-colors",
                highlightedLineId === flag.chat_order!.source_line
                  ? "evidence-highlight"
                  : "",
              ].join(" ")}
            >
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-zinc-300 sm:grid-cols-3">
                <div>
                  <dt className="text-zinc-500">Line #</dt>
                  <dd className="font-semibold text-blue-300">
                    {flag.chat_order!.source_line}
                  </dd>
                </div>
                {flag.chat_order!.date && (
                  <div>
                    <dt className="text-zinc-500">Date</dt>
                    <dd>{flag.chat_order!.date}</dd>
                  </div>
                )}
                {flag.chat_order!.sender && (
                  <div>
                    <dt className="text-zinc-500">Sender</dt>
                    <dd>{flag.chat_order!.sender}</dd>
                  </div>
                )}
                {flag.chat_order!.item && (
                  <div>
                    <dt className="text-zinc-500">Item</dt>
                    <dd>{flag.chat_order!.item}</dd>
                  </div>
                )}
                {flag.chat_order!.quantity != null && (
                  <div>
                    <dt className="text-zinc-500">Qty</dt>
                    <dd>
                      {flag.chat_order!.quantity}{" "}
                      {flag.chat_order!.unit ?? ""}
                    </dd>
                  </div>
                )}
                {flag.chat_order!.amount_pkr != null && (
                  <div>
                    <dt className="text-zinc-500">Amount</dt>
                    <dd className="font-semibold">
                      Rs {flag.chat_order!.amount_pkr}
                    </dd>
                  </div>
                )}
                <div>
                  <dt className="text-zinc-500">Status</dt>
                  <dd>{flag.chat_order!.payment_status}</dd>
                </div>
                <div>
                  <dt className="text-zinc-500">Confidence</dt>
                  <dd>{flag.chat_order!.confidence}</dd>
                </div>
              </dl>
            </div>
          </div>
        )}

        {/* ── Ledger rows evidence panel ── */}
        {hasLedgerRows && (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Ledger row{flag.ledger_rows.length > 1 ? "s" : ""} involved
            </h3>
            <div className="overflow-x-auto rounded-xl border border-green-700/30 bg-green-950/10">
              <table
                className="w-full text-left text-zinc-300"
                aria-label="Ledger rows for this flag"
              >
                <thead>
                  <tr className="border-b border-zinc-700 bg-zinc-800/40 text-xs uppercase tracking-wide text-zinc-500">
                    <th className="px-2 py-2">#</th>
                    <th className="px-2 py-2">Date</th>
                    <th className="px-2 py-2">Customer</th>
                    <th className="px-2 py-2">Item</th>
                    <th className="px-2 py-2">Qty</th>
                    <th className="px-2 py-2">Amount</th>
                    <th className="px-2 py-2">Paid</th>
                  </tr>
                </thead>
                <tbody>
                  {flag.ledger_rows.map((lr) => (
                    <LedgerEvidenceRow
                      key={lr.row_index}
                      row={lr}
                      highlighted={highlightedRowIndex === lr.row_index}
                      rowRef={(el) => {
                        if (el) ledgerRowRefs.current.set(lr.row_index, el);
                        else ledgerRowRefs.current.delete(lr.row_index);
                      }}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ── Fix description ── */}
        {flag.fix_description && (
          <p className="text-xs italic text-zinc-500">{flag.fix_description}</p>
        )}

        {/* ── Edit form ── */}
        {editMode && (
          <div className="flex flex-col gap-4 rounded-xl border border-yellow-700/40 bg-yellow-950/20 p-4">
            <p className="text-xs font-semibold text-yellow-400">
              Edit values
            </p>
            <div className="flex flex-wrap gap-4">
              <label className="flex flex-col gap-1 text-xs text-zinc-400">
                Amount (Rs)
                <input
                  type="number"
                  value={editAmount}
                  onChange={(e) => setEditAmount(e.target.value)}
                  placeholder="e.g. 500"
                  className="min-h-[44px] w-36 rounded-lg border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:ring-2 focus:ring-yellow-500"
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
            <div className="flex flex-wrap gap-2">
              <button
                disabled={fixing}
                onClick={() => {
                  const patch: Record<string, unknown> = {};
                  if (editAmount.trim())
                    patch.amount_pkr = parseFloat(editAmount);
                  if (editPaid === "true") patch.paid = true;
                  if (editPaid === "false") patch.paid = false;
                  void onFix(
                    flag.flag_id,
                    "edit",
                    Object.keys(patch).length ? patch : undefined
                  );
                  setEditMode(false);
                }}
                className="min-h-[44px] rounded-lg bg-yellow-700 px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-yellow-600 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-yellow-500"
              >
                {fixing ? "Saving…" : "Save edit"}
              </button>
              <button
                onClick={() => setEditMode(false)}
                className="min-h-[44px] rounded-lg border border-zinc-600 px-5 py-2 text-sm text-zinc-400 transition-colors hover:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-500"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* ── Accept / Edit / Dismiss ── */}
        {!editMode && (
          <div className="flex flex-wrap gap-3">
            <button
              disabled={fixing}
              onClick={() => void onFix(flag.flag_id, "accept")}
              aria-label={`Accept fix for flag ${flag.flag_id}`}
              className="min-h-[48px] rounded-xl bg-green-800 px-6 py-2.5 text-sm font-bold text-white transition-colors hover:bg-green-700 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-green-500"
            >
              {fixing ? "…" : "✔ Accept"}
            </button>
            <button
              disabled={fixing}
              onClick={() => {
                setEditAmount("");
                setEditPaid("");
                setEditMode(true);
              }}
              aria-label={`Edit flag ${flag.flag_id}`}
              className="min-h-[48px] rounded-xl bg-yellow-800 px-6 py-2.5 text-sm font-bold text-white transition-colors hover:bg-yellow-700 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-yellow-500"
            >
              ✏️ Edit
            </button>
            <button
              disabled={fixing}
              onClick={() => void onFix(flag.flag_id, "dismiss")}
              aria-label={`Dismiss flag ${flag.flag_id}`}
              className="min-h-[48px] rounded-xl border border-zinc-600 bg-zinc-800 px-6 py-2.5 text-sm text-zinc-400 transition-colors hover:bg-zinc-700 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-zinc-500"
            >
              ✕ Dismiss
            </button>
          </div>
        )}

        {/* ── Draft reply — only for flags with an unpaid chat order ── */}
        {hasChatOrder && flag.chat_order!.payment_status !== "paid" && (
          <DraftReply order={flag.chat_order!} />
        )}
      </div>
    </article>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------
function EmptyState() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-zinc-950 px-4 text-zinc-100">
      <div className="flex max-w-sm flex-col items-center gap-3 text-center">
        <span className="text-6xl">⚗️</span>
        <h1 className="text-2xl font-bold text-zinc-100">No session data</h1>
        <p className="text-sm text-zinc-400">
          Upload your files and run the analysis first, then come back here.
        </p>
        <Link
          href="/"
          className="mt-2 flex min-h-[52px] items-center justify-center rounded-xl bg-red-700 px-8 py-3 text-base font-bold text-white transition-colors hover:bg-red-600 focus:outline-none focus:ring-2 focus:ring-red-500"
        >
          ← Upload files
        </Link>
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function FlagsPage() {
  const [flags, setFlags] = useState<Flag[] | null>(null);
  const [reconciled, setReconciled] = useState<LedgerRow[] | null>(null);
  const [totals, setTotals] = useState<Totals | null>(null);
  const [isSample, setIsSample] = useState(false);
  const [agentMode, setAgentMode] = useState<AgentStatus | null>(null);
  const [loaded, setLoaded] = useState(false);

  const [fixingId, setFixingId] = useState<string | null>(null);
  const [fixErr, setFixErr] = useState<string | null>(null);

  // Load from sessionStorage (client-only)
  useEffect(() => {
    const session = readSession();
    if (session) {
      setFlags(session.flags);
      setReconciled(session.reconciled);
      setTotals(session.totals);
      setIsSample(session.isSample);
      setAgentMode(session.mode);
    }
    setLoaded(true);
  }, []);

  const handleFix = useCallback(
    async (
      flagId: string,
      action: "accept" | "edit" | "dismiss",
      patch?: Record<string, unknown>
    ) => {
      setFixingId(flagId);
      setFixErr(null);
      try {
        const result = await reconcileFix(flagId, action, patch);
        setFlags(result.flags);
        setReconciled(result.reconciled);
        setTotals(result.totals);
        writeSession(result.reconciled, result.flags, result.totals);
      } catch (e) {
        setFixErr(
          e instanceof ApiError ? e.detail : "Fix failed — is the backend running?"
        );
      } finally {
        setFixingId(null);
      }
    },
    []
  );

  if (!loaded) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-zinc-950">
        <span className="animate-pulse text-sm text-zinc-500">Loading…</span>
      </main>
    );
  }

  if (!flags || !totals || !reconciled) {
    return <EmptyState />;
  }

  const activeFlags = flags.filter((f) => !f.dismissed);

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      {/* ── Header ── */}
      <header className="sticky top-0 z-10 border-b border-zinc-800 bg-zinc-900/95 px-4 py-3 backdrop-blur sm:px-8">
        <div className="mx-auto flex max-w-3xl flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <Link
              href="/dashboard"
              className="text-sm text-zinc-500 transition-colors hover:text-zinc-300"
              aria-label="Back to dashboard"
            >
              ← Dashboard
            </Link>
            <h1 className="text-xl font-extrabold text-zinc-100">
              ⚗️ Flags{" "}
              <span className="text-sm font-normal text-zinc-500">
                ({activeFlags.length} open)
              </span>
            </h1>
          </div>
          <ModeBadge mode={agentMode} />
        </div>
      </header>

      <div className="mx-auto flex max-w-3xl flex-col gap-7 px-4 py-6 sm:px-8">
        {/* ── Banners ── */}
        {isSample && <SampleBanner />}

        {/* ── Totals (compact) ── */}
        {totals && <TotalsBar totals={totals} />}

        {/* ── Fix error ── */}
        {fixErr && (
          <div
            role="alert"
            className="rounded-xl border border-red-600/50 bg-red-950/30 px-4 py-3 text-sm text-red-300"
          >
            {fixErr}
          </div>
        )}

        {/* ── Flag count summary ── */}
        <div className="flex items-center justify-between">
          <p className="text-sm text-zinc-400">
            {activeFlags.length === 0
              ? "All flags resolved — nothing left to action."
              : `${activeFlags.length} flag${activeFlags.length !== 1 ? "s" : ""} need your attention.`}
          </p>
          {flags.length !== activeFlags.length && (
            <span className="text-xs text-zinc-600">
              {flags.length - activeFlags.length} dismissed
            </span>
          )}
        </div>

        {/* ── Flag cards ── */}
        {flags.length === 0 ? (
          <p className="py-8 text-center text-sm text-zinc-500">No flags.</p>
        ) : (
          <div className="flex flex-col gap-5">
            {flags.map((flag) => (
              <FlagDetail
                key={flag.flag_id}
                flag={flag}
                onFix={handleFix}
                fixing={fixingId === flag.flag_id}
              />
            ))}
          </div>
        )}

        {/* ── Footer ── */}
        <footer className="flex flex-col gap-1 border-t border-zinc-800 pt-6 text-xs text-zinc-600">
          <p>Built with Kiro — FrankenLedger, Kiroween 2026.</p>
          <p>
            No WhatsApp API. No payments. No accounts. Nothing stored after
            your session.
          </p>
          {isSample && (
            <p className="text-amber-700">
              Sample data shown is fictional — Noor General Store does not
              exist.
            </p>
          )}
        </footer>
      </div>
    </main>
  );
}
