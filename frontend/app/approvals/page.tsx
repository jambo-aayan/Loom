"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, Insight, Signal, Strategy } from "@/lib/api";

function ApprovalsList() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [insights, setInsights] = useState<Record<string, Insight[]>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [strategyStyles, setStrategyStyles] = useState<Record<string, string>>({});
  const [researching, setResearching] = useState<string | null>(null);
  const [deciding, setDeciding] = useState<string | null>(null);
  const [lastBooked, setLastBooked] = useState<{ instrument: string; realized_pnl: number; realized_pnl_pct: number } | null>(
    null,
  );
  const highlightedSignalId = useSearchParams().get("signal");

  async function load() {
    try {
      const [pending, strategies] = await Promise.all([api.signals("demo", "pending_approval"), api.strategies()]);
      setSignals(pending);
      setStrategyStyles(Object.fromEntries(strategies.map((s: Strategy) => [s.id, s.style])));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!highlightedSignalId) return;
    document.getElementById(`signal-${highlightedSignalId}`)?.scrollIntoView({ block: "center" });
  }, [highlightedSignalId, signals]);

  async function screen(signalId: string) {
    const insight = await api.screenSignal(signalId);
    setInsights((prev) => ({ ...prev, [signalId]: [...(prev[signalId] ?? []), insight] }));
  }

  async function research(signalId: string) {
    const confirmed = window.confirm(
      "Deep research uses a paid model and costs real money per call. Continue?",
    );
    if (!confirmed) return;
    setResearching(signalId);
    try {
      const insight = await api.researchSignal(signalId);
      setInsights((prev) => ({ ...prev, [signalId]: [...(prev[signalId] ?? []), insight] }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setResearching(null);
    }
  }

  async function decide(signalId: string, decision: "approve" | "reject") {
    if (deciding) return; // a click already in flight for some signal — ignore repeats/other clicks
    setDeciding(signalId);
    const note = notes[signalId];
    try {
      if (decision === "approve") {
        const decided = await api.approveSignal(signalId, note);
        setLastBooked(decided.booked_trade);
      } else {
        await api.rejectSignal(signalId, note);
      }
      setError(null);
      await load();
    } catch (e) {
      // A prior attempt on this exact signal may have already succeeded server-side even though
      // this request failed (a dropped response, a retry) — a 409 here means it already went
      // through, so just refresh instead of showing a confusing "already approved" error for
      // what the user experiences as their first click.
      const message = (e as Error).message;
      if (message.includes("-> 409")) {
        await load();
      } else {
        setError(message);
      }
    } finally {
      setDeciding(null);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl">Approvals</h1>
      {error && <p className="text-danger text-sm">{error}</p>}
      {lastBooked && (
        <div
          className={`rounded-xl p-3 text-sm flex items-center justify-between ${
            lastBooked.realized_pnl >= 0 ? "bg-mint/15" : "bg-danger/15"
          }`}
        >
          <span className="font-numeric">
            Sold {lastBooked.instrument}, booked {lastBooked.realized_pnl >= 0 ? "+" : ""}£
            {lastBooked.realized_pnl.toFixed(2)} ({lastBooked.realized_pnl >= 0 ? "+" : ""}
            {(lastBooked.realized_pnl_pct * 100).toFixed(1)}%)
          </span>
          <button onClick={() => setLastBooked(null)} className="text-xs underline shrink-0 ml-3">
            Dismiss
          </button>
        </div>
      )}
      {signals.length === 0 && !error && (
        <p className="text-sm text-neutral-500">Nothing pending — run a trading pass from Overview.</p>
      )}
      <div className="space-y-3">
        {signals.map((signal) => (
          <div
            key={signal.id}
            id={`signal-${signal.id}`}
            className={`rounded-2xl border p-4 space-y-3 ${
              signal.id === highlightedSignalId
                ? "border-indigo dark:border-indigo-dark ring-2 ring-indigo/40 dark:ring-indigo-dark/40"
                : "border-black/10 dark:border-white/10"
            }`}
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="font-medium">
                  {signal.action.toUpperCase()} {signal.instrument}
                </p>
                <p className="text-sm text-neutral-500 font-numeric">
                  @ £{signal.reference_price.toFixed(2)} · confidence {(signal.confidence * 100).toFixed(0)}%
                </p>
                {signal.signal_type === "entry" && (
                  <p className="text-sm text-neutral-500 font-numeric">
                    ~{signal.quantity.toFixed(4)} units · ~£{(signal.quantity * signal.reference_price).toFixed(2)}
                    {" "}
                    <span className="text-xs">(proposed — re-sized against risk limits at approval)</span>
                  </p>
                )}
              </div>
              <span className="text-xs rounded-full px-2 py-1 bg-amber/15 text-amber dark:text-amber-dark">
                {signal.status.replace("_", " ")}
              </span>
            </div>

            <div className="text-xs text-neutral-500 font-numeric">
              target {signal.exit_plan.profit_target_pct != null ? `${(signal.exit_plan.profit_target_pct * 100).toFixed(1)}%` : "—"}
              {" · "}
              stop {signal.exit_plan.stop_loss_pct != null ? `${(signal.exit_plan.stop_loss_pct * 100).toFixed(1)}%` : "—"}
            </div>

            {(insights[signal.id] ?? []).map((insight) => (
              <div key={insight.id} className="text-sm bg-black/5 dark:bg-white/5 rounded-xl p-3 space-y-1">
                <span
                  className={`text-xs rounded-full px-2 py-0.5 ${
                    insight.tier === "research" ? "bg-indigo/15 text-indigo dark:text-indigo-dark" : "bg-black/10 dark:bg-white/10"
                  }`}
                >
                  {insight.tier === "research" ? "Research" : "Screening"}
                </span>
                <p>{insight.content}</p>
              </div>
            ))}
            <div className="flex flex-wrap gap-3">
              {!(insights[signal.id] ?? []).length && (
                <button onClick={() => screen(signal.id)} className="text-xs text-indigo dark:text-indigo-dark underline">
                  Generate Insight commentary
                </button>
              )}
              {strategyStyles[signal.strategy_id] === "investment" && (
                <button
                  onClick={() => research(signal.id)}
                  disabled={researching === signal.id}
                  className="text-xs text-indigo dark:text-indigo-dark underline disabled:opacity-50"
                >
                  {researching === signal.id
                    ? "Researching…"
                    : (insights[signal.id] ?? []).some((i) => i.tier === "research")
                      ? "Re-run deep research (paid)"
                      : "Deep research (paid)"}
                </button>
              )}
            </div>

            <input
              placeholder="Optional note"
              value={notes[signal.id] ?? ""}
              onChange={(e) => setNotes((prev) => ({ ...prev, [signal.id]: e.target.value }))}
              className="w-full rounded-lg border border-black/10 dark:border-white/10 bg-transparent px-3 py-1.5 text-sm"
            />

            <div className="flex gap-2">
              <button
                onClick={() => decide(signal.id, "approve")}
                disabled={deciding === signal.id}
                className="flex-1 rounded-full bg-mint text-black py-1.5 text-sm font-medium disabled:opacity-50"
              >
                {deciding === signal.id ? "Approving…" : "Approve"}
              </button>
              <button
                onClick={() => decide(signal.id, "reject")}
                disabled={deciding === signal.id}
                className="flex-1 rounded-full bg-pink text-black py-1.5 text-sm font-medium disabled:opacity-50"
              >
                {deciding === signal.id ? "Rejecting…" : "Reject"}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ApprovalsPage() {
  return (
    <Suspense fallback={null}>
      <ApprovalsList />
    </Suspense>
  );
}
