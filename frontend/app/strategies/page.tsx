"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ExitObservations, Strategy } from "@/lib/api";

function ExitPassReview({ data }: { data: ExitObservations }) {
  if (data.total === 0) {
    return (
      <p className="text-sm text-neutral-500">
        Nothing yet. The exit pass runs every 30 minutes through the trading day and records what it would have
        closed.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {data.by_strategy.map((group) => (
        <div key={group.strategy}>
          <div className="flex items-baseline justify-between gap-2">
            <p className="font-medium">{group.strategy}</p>
            <p className="text-xs text-neutral-500 font-numeric">
              {group.count} would have exited
              {group.fast_stops > 0 && (
                <>
                  {" · "}
                  <span className="text-pink">{group.fast_stops} within {data.fast_stop_days}d</span>
                </>
              )}
            </p>
          </div>

          <div className="mt-2 space-y-1">
            {group.decisions.map((d) => (
              <div
                key={d.id}
                className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 rounded-lg border border-black/10 dark:border-white/10 px-3 py-2 text-sm"
              >
                <span className="font-medium">{d.instrument}</span>
                <span
                  className={`text-xs rounded-full px-2 py-0.5 ${
                    d.fast_stop ? "bg-pink/20" : "bg-black/10 dark:bg-white/10"
                  }`}
                >
                  {d.exit_reason}
                </span>
                <span className="text-xs text-neutral-500 font-numeric">
                  {d.quantity.toLocaleString(undefined, { maximumFractionDigits: 4 })} @ £
                  {d.decision_price.toFixed(2)}
                </span>
                <span className="text-xs text-neutral-500 font-numeric ml-auto">
                  {d.hold_days !== null ? `held ${d.hold_days}d` : "hold unknown"}
                  {d.entry_date && ` · from ${d.entry_date}`}
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [observations, setObservations] = useState<ExitObservations | null>(null);

  useEffect(() => {
    api.strategies().then(setStrategies);
    api.exitObservations("demo").then(setObservations).catch(() => setObservations(null));
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl">Strategies</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
        {strategies.map((s) => (
          <Link
            key={s.id}
            href={`/strategies/${s.id}`}
            className="block rounded-xl border border-black/10 dark:border-white/10 p-4 hover:bg-black/5 dark:hover:bg-white/5"
          >
            <p className="font-medium">{s.name}</p>
            <p className="text-xs text-neutral-500">
              {s.style} · {s.live_enabled ? "live-enabled" : "demo only"}
            </p>
          </Link>
        ))}
      </div>

      <div className="rounded-2xl border border-black/10 dark:border-white/10 p-5 space-y-3">
        <div>
          <h2 className="text-lg">Exit pass — what it would have closed</h2>
          <p className="text-xs text-neutral-500 mt-1">
            While observing, nothing is sold. Read this as a check on the <em>parameters</em>, not just the layer:
            none of these stops or targets has ever fired in live trading, so none has been tested against real
            prices. A stop firing within {observations?.fast_stop_days ?? 5} days of entry is usually measuring
            noise rather than risk — those are marked.
          </p>
        </div>
        {observations ? <ExitPassReview data={observations} /> : <p className="text-sm text-neutral-500">Loading…</p>}
      </div>
    </div>
  );
}
