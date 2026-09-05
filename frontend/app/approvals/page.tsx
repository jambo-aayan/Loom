"use client";

import { useEffect, useState } from "react";
import { api, Insight, Signal } from "@/lib/api";

export default function ApprovalsPage() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [insights, setInsights] = useState<Record<string, Insight[]>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const pending = await api.signals("demo", "pending_approval");
      setSignals(pending);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function screen(signalId: string) {
    const insight = await api.screenSignal(signalId);
    setInsights((prev) => ({ ...prev, [signalId]: [...(prev[signalId] ?? []), insight] }));
  }

  async function decide(signalId: string, decision: "approve" | "reject") {
    const note = notes[signalId];
    if (decision === "approve") {
      await api.approveSignal(signalId, note);
    } else {
      await api.rejectSignal(signalId, note);
    }
    await load();
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl">Approvals</h1>
      {error && <p className="text-danger text-sm">{error}</p>}
      {signals.length === 0 && !error && (
        <p className="text-sm text-neutral-500">Nothing pending — run a trading pass from Overview.</p>
      )}
      <div className="space-y-3">
        {signals.map((signal) => (
          <div key={signal.id} className="rounded-2xl border border-black/10 dark:border-white/10 p-4 space-y-3">
            <div className="flex items-start justify-between">
              <div>
                <p className="font-medium">
                  {signal.action.toUpperCase()} {signal.instrument}
                </p>
                <p className="text-sm text-neutral-500 font-numeric">
                  @ £{signal.reference_price.toFixed(2)} · confidence {(signal.confidence * 100).toFixed(0)}%
                </p>
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
              <p key={insight.id} className="text-sm bg-black/5 dark:bg-white/5 rounded-xl p-3">
                {insight.content}
              </p>
            ))}
            {!(insights[signal.id] ?? []).length && (
              <button onClick={() => screen(signal.id)} className="text-xs text-indigo dark:text-indigo-dark underline">
                Generate Insight commentary
              </button>
            )}

            <input
              placeholder="Optional note"
              value={notes[signal.id] ?? ""}
              onChange={(e) => setNotes((prev) => ({ ...prev, [signal.id]: e.target.value }))}
              className="w-full rounded-lg border border-black/10 dark:border-white/10 bg-transparent px-3 py-1.5 text-sm"
            />

            <div className="flex gap-2">
              <button
                onClick={() => decide(signal.id, "approve")}
                className="flex-1 rounded-full bg-mint text-black py-1.5 text-sm font-medium"
              >
                Approve
              </button>
              <button
                onClick={() => decide(signal.id, "reject")}
                className="flex-1 rounded-full bg-pink text-black py-1.5 text-sm font-medium"
              >
                Reject
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
