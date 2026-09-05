"use client";

import { useEffect, useState } from "react";
import { api, Insight, Signal } from "@/lib/api";

export default function InsightsPage() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [insights, setInsights] = useState<Record<string, Insight[]>>({});

  useEffect(() => {
    api.signals("demo").then(async (all) => {
      setSignals(all);
      const entries = await Promise.all(all.map(async (s) => [s.id, await api.signalInsights(s.id)] as const));
      setInsights(Object.fromEntries(entries));
    });
  }, []);

  const withInsights = signals.filter((s) => (insights[s.id] ?? []).length > 0);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl">Insights</h1>
      <p className="text-sm text-neutral-500">
        The cheap screening tier runs per signal from Approvals. A rolled-up daily/weekly digest and
        chart-annotated triggers are M3 scope (ticket #42).
      </p>
      {withInsights.length === 0 && <p className="text-sm text-neutral-500">No Insight commentary generated yet.</p>}
      <div className="space-y-2">
        {withInsights.map((s) => (
          <div key={s.id} className="rounded-xl border border-black/10 dark:border-white/10 p-3">
            <p className="font-medium text-sm">
              {s.action} {s.instrument}
            </p>
            {insights[s.id].map((i) => (
              <p key={i.id} className="text-sm text-neutral-500 mt-1">
                {i.content}
              </p>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
