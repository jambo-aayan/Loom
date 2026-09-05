"use client";

import { useEffect, useState } from "react";
import { api, Signal } from "@/lib/api";

export default function HistoryPage() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .history("demo")
      .then(setSignals)
      .catch((e) => setError((e as Error).message));
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl">History</h1>
      {error && <p className="text-danger text-sm">{error}</p>}
      {signals.length === 0 && !error && <p className="text-sm text-neutral-500">No decisions yet.</p>}
      <div className="space-y-2">
        {signals.map((s) => (
          <div key={s.id} className="rounded-xl border border-black/10 dark:border-white/10 p-3">
            <div className="flex items-center justify-between">
              <p className="font-medium">
                {s.action.toUpperCase()} {s.instrument}
              </p>
              <span
                className={`text-xs rounded-full px-2 py-1 ${
                  s.status === "rejected" ? "bg-pink/20" : "bg-mint/20"
                }`}
              >
                {s.status}
              </span>
            </div>
            {s.status === "executed" || s.status === "approved" ? (
              <p className="text-xs text-neutral-500 mt-1">Actual outcome tracked from real fills.</p>
            ) : s.counterfactual_outcome ? (
              <p className="text-xs text-neutral-500 mt-1">
                Counterfactual: {String(s.counterfactual_outcome.status)} —{" "}
                {typeof s.counterfactual_outcome.return_pct === "number"
                  ? `${(s.counterfactual_outcome.return_pct * 100).toFixed(1)}%`
                  : "n/a"}
              </p>
            ) : (
              <p className="text-xs text-neutral-500 mt-1">Counterfactual not yet simulated.</p>
            )}
            {s.note && <p className="text-xs italic mt-1">“{s.note}”</p>}
          </div>
        ))}
      </div>
    </div>
  );
}
